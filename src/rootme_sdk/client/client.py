"""The small public facade combining official API reads and discovered web forms."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import TracebackType
from typing import Self
from urllib.parse import parse_qs, urlsplit

import httpx

from ..authentication.credentials import Credentials
from ..authentication.session import API_HOST, WEB_HOST, Session, SessionCookie
from ..errors import (
    AuthenticationRequiredError,
    HumanInterventionRequiredError,
    NetworkError,
    NotFoundError,
    RateLimitedError,
    UnexpectedResponseError,
)
from ..models import (
    CATEGORY_RUBRIQUES,
    DIFFICULTY_SCORES,
    Category,
    Challenge,
    ChallengeSummary,
    Collection,
    Difficulty,
    JSONObject,
    JSONValue,
    Resource,
    SubmissionResult,
    SubmissionStatus,
    Upload,
    UserProfile,
    WebForm,
    WebPage,
)
from ..parsers import api, web
from ..transport import Query, Transport, platform_url
from .queries import (
    build_query,
    challenge_query,
    find_form,
    validate_identifier,
    validate_language,
)

# Private aliases for internal methods and backwards-compatibility
_find_form = find_form
_identifier = validate_identifier
_language = validate_language
_query = build_query
_challenge_query = challenge_query

API_URL = f"https://{API_HOST}"
WEB_URL = f"https://{WEB_HOST}"


class RootMeClient:
    """A synchronous Root-Me client owning its HTTP pool and managed browser."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        credentials_file: str | Path | None = None,
        session_file: str | Path | None = None,
        spip_session: str | None = None,
        session: Session | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30,
        read_retries: int = 1,
        max_retry_delay: float = 5,
        min_request_interval: float = 2,
    ) -> None:
        """Connect with credentials, reusing an accepted ``session_file``; none means anonymous."""
        supplied = any(value is not None for value in (username, password, credentials_file))
        if session_file is not None and not supplied:
            raise ValueError("A session file requires login/password or a credentials file.")
        self.session = _initial_session(session, spip_session, supplied)
        self._session_file = None if session_file is None else Path(session_file)
        self._transport = Transport(
            self.session,
            transport=transport,
            timeout=timeout,
            read_retries=read_retries,
            max_retry_delay=max_retry_delay,
            min_request_interval=min_request_interval,
        )
        self._cached_solved_ids: set[int] | None = None
        if supplied:
            self._connect(username, password, credentials_file)

    def _connect(
        self, username: str | None, password: str | None, credentials_file: str | Path | None
    ) -> None:
        """Reuse an accepted saved session or log in; close resources on failure."""
        try:
            credentials = Credentials.load(username, password, credentials_file)
            if not self._resume():
                self.login(credentials.username, credentials.password)
                self._save_session()
        except Exception:
            self.close()
            raise

    def _resume(self) -> bool:
        """Adopt the saved session only while the platform still accepts it.

        A missing or invalid file and an authentication rejection call for a new login.
        Rate limits, network failures and verification gates propagate instead, so a
        transient error never starts a browser login.
        """
        if self._session_file is None:
            return False
        try:
            saved = Session.load(self._session_file)
        except (FileNotFoundError, UnexpectedResponseError):
            return False
        self.session.cookies, self.session.user_agent = saved.cookies, saved.user_agent
        try:
            self.get_profile()
        except AuthenticationRequiredError:
            self.session.cookies = ()
            return False
        return True

    def _save_session(self) -> None:
        """Persist the current login, including renewed cookies, to the session file."""
        if self._session_file is not None and self.session.spip_session:
            self.session.save(self._session_file)

    def __enter__(self) -> Self:
        """Enter the owned resource scope."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client even when a caller operation fails."""
        self.close()

    def close(self) -> None:
        """Save the session file when configured, then release network and browser resources."""
        try:
            self._save_session()
        finally:
            self._transport.close()

    def login(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        credentials_file: str | Path | None = None,
        timeout: float = 180,
    ) -> Session:
        """Connect with credentials, automatically handling the site's JavaScript gate."""
        credentials = Credentials.load(username, password, credentials_file)
        self._cached_solved_ids = None
        self._close_browser()
        self.session.cookies = tuple(c for c in self.session.cookies if c.name != "spip_session")
        try:
            return self._open_browser(credentials, timeout=timeout)
        except Exception:
            self.session.cookies = ()
            raise

    def _open_browser(
        self,
        credentials: Credentials | None = None,
        *,
        timeout: float = 180,
    ) -> Session:
        """Open managed JS access; ordinary password login calls this automatically."""
        from ..authentication.browser import BrowserSession

        self._close_browser()
        browser = BrowserSession(self.session, timeout=timeout)
        try:
            result = (
                browser.authenticate(credentials.username, credentials.password)
                if credentials
                else browser.prepare()
            )
        except Exception:
            browser.close()
            raise
        self._transport.browser = browser
        return result

    def _close_browser(self) -> None:
        """Discard an owned browser before a new authentication attempt."""
        if self._transport.browser:
            self._transport.browser.close()
            self._transport.browser = None

    def logout(self) -> None:
        """Invalidate the web session when present, then always erase local credentials."""
        try:
            if self.session.spip_session:
                self._transport.request("GET", f"{WEB_URL}/?action=logout", mutation=True)
        finally:
            self.session.cookies = ()
            if self._session_file is not None:
                self._session_file.unlink(missing_ok=True)
            self._close_browser()
            self._cached_solved_ids = None

    def get_challenge(self, reference: int | str) -> Challenge:
        """Fetch the complete challenge with full statement, resources and metadata.

        Args:
            reference: Numeric challenge ID or full website challenge URL.

        Returns:
            Challenge: Complete challenge with statement and resources.
        """
        url = self._challenge_url(reference)
        document = self._get_page(url)
        cid = reference if isinstance(reference, int) else None
        is_solved = (cid in self._user_solved_ids) if cid is not None else None
        ch = web.challenge_page(document, solved=is_solved)
        target_id = ch.id or cid
        if target_id is not None and target_id in self._user_solved_ids and not ch.solved:
            return replace(ch, solved=True)
        return ch

    def read_challenge(self, reference: int | str) -> Challenge:
        """Read the complete challenge statement, resources and metadata.

        Args:
            reference: Numeric challenge ID or full website challenge URL.

        Returns:
            Challenge: Complete challenge with statement and resources.
        """
        return self.get_challenge(reference)

    @property
    def _user_solved_ids(self) -> set[int]:
        """Return the set of challenge IDs validated by the authenticated user."""
        if self._cached_solved_ids is None:
            self._cached_solved_ids = self._load_user_solved_ids()
        return self._cached_solved_ids

    def _load_user_solved_ids(self) -> set[int]:
        """Fetch solved challenge IDs from user validations when authenticated."""
        cookie = self.session.spip_session
        if not cookie or not cookie.split("_")[0].isdecimal():
            return set()
        validations = self.get_profile().data.get("validations", [])
        result = set()
        for record in api.records(validations):
            identifier = api.integer(record, "id_challenge", required=True)
            assert identifier is not None
            result.add(identifier)
        return result

    def search_challenges(
        self,
        *,
        query: str | None = None,
        category: Category | None = None,
        difficulty: Difficulty | None = None,
        score: int | None = None,
        limit: int = 10,
    ) -> Iterator[ChallengeSummary]:
        """Search challenges with native category, query, difficulty and score filters."""
        if limit <= 0:
            raise ValueError("Limit must be a positive integer.")
        if score is not None and score < 0:
            raise ValueError("Score must be a non-negative integer.")
        if (
            difficulty is not None
            and score is not None
            and api.score_to_difficulty(score) != difficulty
        ):
            return
        params: dict[str, str | int] = {}
        if query:
            params["titre"] = query
        if category is not None:
            params["id_rubrique"] = CATEGORY_RUBRIQUES[category]
        yield from self._dispatch_challenge_search(params, difficulty, score, limit)

    def _dispatch_challenge_search(
        self,
        params: dict[str, str | int],
        difficulty: Difficulty | None,
        score: int | None,
        limit: int,
    ) -> Iterator[ChallengeSummary]:
        """Dispatch query according to score or difficulty constraints up to limit."""
        if score is not None:
            scores: tuple[int, ...] = (score,)
        elif difficulty is not None:
            scores = DIFFICULTY_SCORES[difficulty]
        else:
            yield from self._fetch_challenge_summaries(params, None, limit)
            return

        count = 0
        for s in scores:
            for item in self._fetch_challenge_summaries(
                {**params, "score": s}, s, limit - count, difficulty
            ):
                yield item
                count += 1
                if count >= limit:
                    return

    def _fetch_challenge_summaries(
        self,
        params: dict[str, str | int],
        default_score: int | None,
        limit: int,
        expected_difficulty: Difficulty | None = None,
    ) -> Iterator[ChallengeSummary]:
        """Fetch lazy challenge summary pages with bound score up to limit."""
        count = 0
        for summary in self._iterate(
            f"{API_URL}/challenges",
            lambda data: api.challenge_summary(data, default_score=default_score),
            params,
        ):
            if expected_difficulty is not None and summary.difficulty != expected_difficulty:
                continue
            yield summary
            count += 1
            if count >= limit:
                return

    def list_challenges(
        self,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        language: str | None = None,
        lang: str | None = None,
        score: int | None = None,
        author_ids: Sequence[int] = (),
        **extra_filters: str | int,
    ) -> Collection[Challenge]:
        """Read one page using challenge filters documented by the official API.

        Args:
            title: Substring matching the challenge title.
            subtitle: Substring matching the challenge subtitle.
            language: Two-letter language code filter ("en" or "fr").
            lang: Alias for language matching the Root-Me API parameter name.
            score: Exact challenge point score filter.
            author_ids: Sequence of author IDs who created the challenge.
            **extra_filters: Additional raw query parameters sent to the API.

        Returns:
            Collection[Challenge]: Page items and continuation link.
        """
        params = _challenge_query(
            title=title,
            subtitle=subtitle,
            language=language,
            lang=lang,
            score=score,
            author_ids=author_ids,
            **extra_filters,
        )
        return self._collection(f"{API_URL}/challenges", api.challenge, params)

    def iter_challenges(
        self,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        language: str | None = None,
        lang: str | None = None,
        score: int | None = None,
        author_ids: Sequence[int] = (),
        **extra_filters: str | int,
    ) -> Iterator[Challenge]:
        """Iterate server-provided challenge pages using explicit or raw filters.

        Args:
            title: Substring matching the challenge title.
            subtitle: Substring matching the challenge subtitle.
            language: Two-letter language code filter ("en" or "fr").
            lang: Alias for language matching the Root-Me API parameter name.
            score: Exact challenge point score filter.
            author_ids: Sequence of author IDs who created the challenge.
            **extra_filters: Additional raw query parameters sent to the API.

        Yields:
            Challenge: Lazily retrieved challenge instances across pages.
        """
        params = _challenge_query(
            title=title,
            subtitle=subtitle,
            language=language,
            lang=lang,
            score=score,
            author_ids=author_ids,
            **extra_filters,
        )
        yield from self._iterate(f"{API_URL}/challenges", api.challenge, params)

    def get_profile(self, user_id: int | None = None) -> UserProfile:
        """Read a user profile for the current account or a specified account ID.

        Args:
            user_id: Optional numeric account ID (defaults to authenticated account).

        Returns:
            UserProfile: Flat user profile with score, rank, and solved challenges count.
        """
        if user_id is not None:
            _identifier(user_id)
            target_id = user_id
        else:
            target_id = self._current_user_id()
        return api.user(self._one(f"/auteurs/{target_id}"), identifier=target_id)

    def _current_user_id(self) -> int:
        """Extract the numeric author ID from the active spip_session cookie."""
        spip = self.session.spip_session
        if not spip:
            raise AuthenticationRequiredError(
                "Profile inspection requires an authenticated account.", reason="missing"
            )
        prefix = spip.split("_")[0]
        if prefix.isdecimal():
            return int(prefix)
        raise UnexpectedResponseError("Unable to determine current account ID.")

    def get_user(self, identifier: int) -> UserProfile:
        """Read a profile, including the platform's solved-challenge data.

        Args:
            identifier: Numeric account ID of the user.

        Returns:
            UserProfile: Account profile and statistics.
        """
        return self.get_profile(identifier)

    def list_categories(self, *, language: str = "en") -> tuple[Category, ...]:
        """Return all supported challenge categories as standard enums.

        Args:
            language: Interface language code ("en" or "fr").

        Returns:
            tuple[Category, ...]: Supported category enums.
        """
        _language(language)
        return tuple(Category)

    def _get_page(self, url: str) -> WebPage:
        """Read an anonymous or authenticated page and discover its forms and links."""
        if urlsplit(platform_url(url)).hostname != WEB_HOST:
            raise ValueError("Website pages must use the website host.")
        if "action" in parse_qs(urlsplit(url).query):
            raise ValueError("Action links cannot be used for page reads.")
        try:
            response = self._transport.request("GET", url)
        except HumanInterventionRequiredError:
            if self._transport.browser:
                raise
            self._open_browser()
            response = self._transport.request("GET", url)
        return web.page(response.text, str(response.url))

    def preferences(self, *, language: str = "en") -> WebPage:
        """Read editable profile/preferences controls without changing anything.

        Args:
            language: Interface language code ("en" or "fr").

        Returns:
            WebPage: Discovered preferences form and page.
        """
        _language(language)
        if not self.session.spip_session:
            raise AuthenticationRequiredError("Preferences require a web session.")
        document = self._get_page(f"{WEB_URL}/?page=preferences&lang={language}")
        _find_form(document, "modifier_auteur")
        return document

    def update_preferences(
        self, changes: Mapping[str, str], *, files: Mapping[str, Upload] | None = None
    ) -> WebPage:
        """Explicitly update fields exposed by the verified modifier_auteur form.

        Args:
            changes: Mapping of field names to new text values.
            files: Optional mapping of upload control names to Upload instances.

        Returns:
            WebPage: Resulting preferences page after submission.
        """
        form = _find_form(self.preferences(), "modifier_auteur")
        return self._submit_form(form, changes, files=files)

    def _submit_form(
        self,
        form: WebForm,
        changes: Mapping[str, str],
        *,
        files: Mapping[str, Upload] | None = None,
    ) -> WebPage:
        """Refresh tokens and submit one explicitly chosen form, including file uploads."""
        current = _find_form(self._get_page(form.page_url), form.name)
        values = web.form_values(current, changes)
        allowed = {f.name for f in current.fields if f.kind == "file"}
        if files and not set(files).issubset(allowed):
            raise ValueError("Unknown file upload control.")
        uploads = {
            name: (file.filename, file.content, file.content_type)
            for name, file in (files or {}).items()
        }
        options = {"params": values} if current.method == "GET" else {"data": values}
        response = self._transport.request(
            current.method,
            current.action,
            **options,
            files=uploads or None,
            mutation=True,
            authenticated=current.name != "login",
        )
        return web.page(response.text, str(response.url))

    def submit_flag(self, challenge_id: int, flag: str) -> SubmissionResult:
        """Submit a flag for a challenge and receive a standardized verdict.

        Args:
            challenge_id: Numeric ID of the challenge to validate.
            flag: The secret flag/answer string to submit.

        Returns:
            SubmissionResult: The submission outcome and server message.
        """
        return self.submit_answer(challenge_id, flag)

    def submit_answer(self, reference: int | str, answer: str) -> SubmissionResult:
        """Submit exactly once and report uncertainty rather than replaying an answer.

        Args:
            reference: Numeric challenge ID or full website challenge URL.
            answer: Proposed answer string to validate.

        Returns:
            SubmissionResult: Structured outcome with status and feedback.
        """
        if not answer:
            raise ValueError("An answer must be nonempty.")
        document = self._get_page(self._challenge_url(reference))
        known = web.submission_result(document, answer)
        if known.status == SubmissionStatus.ALREADY_SOLVED:
            return known
        form = _find_form(document, "validation_challenge")
        try:
            result = self._submit_form(form, {"passe": answer})
        except RateLimitedError as error:
            return SubmissionResult(SubmissionStatus.BLOCKED, retry_after=error.retry_after)
        except (NetworkError, UnexpectedResponseError):
            return SubmissionResult(SubmissionStatus.INDETERMINATE)
        outcome = web.submission_result(result, answer)
        if outcome.status == SubmissionStatus.ACCEPTED:
            self._cached_solved_ids = None
        return outcome

    def download(self, resource: Resource | str, destination: str | Path | None = None) -> bytes:
        """Download a public HTTPS attachment without account credentials.

        Args:
            resource: Resource instance from a challenge or direct download URL.
            destination: Optional file path, or existing directory where the file keeps
                the name from its URL, to save the downloaded bytes.

        Returns:
            bytes: The downloaded file contents.
        """
        target = resource if isinstance(resource, Resource) else Resource(resource)
        data = self._transport.download(target.url)
        if destination is not None:
            path = Path(destination)
            (path / target.filename if path.is_dir() else path).write_bytes(data)
        return data

    def download_files(
        self, challenge: Challenge | int | str, directory: str | Path = "."
    ) -> tuple[Path, ...]:
        """Download every challenge file, keeping the names from their URLs.

        Args:
            challenge: Challenge, numeric challenge ID or website challenge URL whose
                ``files`` are downloaded; ``resources`` are not.
            directory: Directory created when missing, the current one by default;
                existing files are overwritten.

        Returns:
            tuple[Path, ...]: Paths of the written files, in ``challenge.files`` order.
        """
        if not isinstance(challenge, Challenge):
            challenge = self.get_challenge(challenge)
        folder = Path(directory)
        paths = tuple(folder / file.filename for file in challenge.files)
        folder.mkdir(parents=True, exist_ok=True)
        for file, path in zip(challenge.files, paths, strict=True):
            path.write_bytes(self._transport.download(file.url))
        return paths

    def _challenge_url(self, reference: int | str) -> str:
        """Resolve a challenge reference without constructing an unverified web route."""
        if isinstance(reference, str):
            return platform_url(reference)
        _identifier(reference)
        data = self._one(f"/challenges/{reference}")
        url = api.challenge(data, identifier=reference).url
        if not url:
            raise UnexpectedResponseError("API did not provide a challenge URL.")
        return platform_url(url)

    def _one(self, path: str) -> JSONObject:
        """Require exactly one data record in a detail response."""
        data = api.records(self._api(f"{API_URL}{path}"))
        if len(data) != 1:
            raise UnexpectedResponseError("Expected one API detail record.")
        return data[0]

    def _api(self, url: str, params: Query | None = None) -> JSONValue:
        """Read and validate JSON from the exact official API host."""
        if urlsplit(platform_url(url)).hostname != API_HOST:
            raise UnexpectedResponseError("API continuation points outside the API.")
        response = self._transport.request("GET", url, params=params, authenticated=True)
        return api.json_payload(response.text)

    def _collection[T](
        self, url: str, parse: Callable[[JSONObject], T], params: Query | None = None
    ) -> Collection[T]:
        """Preserve the server's continuation link alongside parsed records."""
        try:
            data = self._api(url, params)
        except NotFoundError:
            return Collection((), None)
        values = data if isinstance(data, list) else [data]
        next_url = next(
            (
                str(v["href"])
                for v in values
                if isinstance(v, dict) and v.get("rel") == "next" and isinstance(v.get("href"), str)
            ),
            None,
        )
        return Collection(tuple(parse(record) for record in api.records(data)), next_url)

    def _iterate[T](
        self, url: str, parse: Callable[[JSONObject], T], params: Query | None = None
    ) -> Iterator[T]:
        """Follow server pagination lazily, rejecting cycles and untrusted hosts."""
        seen = set()
        while url:
            if url in seen:
                raise UnexpectedResponseError("API pagination cycle detected.")
            seen.add(url)
            result = self._collection(url, parse, params)
            yield from result.items
            url, params = result.next_url or "", None


def _initial_session(session: Session | None, cookie: str | None, supplied: bool) -> Session:
    """Keep explicit session reuse separate from supplied account credentials."""
    if (
        session is not None
        and cookie is not None
        or supplied
        and (session is not None or cookie is not None)
    ):
        raise ValueError("Supply login/password, a session or a session cookie, not several.")
    cookies = (SessionCookie("spip_session", cookie),) if cookie else ()
    return session or Session(cookies=cookies)
