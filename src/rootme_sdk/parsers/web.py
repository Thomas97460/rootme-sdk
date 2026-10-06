"""Discover real website forms and parse challenge pages without guessed routes."""

import re
from collections.abc import Mapping
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from ..errors import AuthenticationRequiredError, UnexpectedResponseError
from ..models import (
    CATEGORY_RUBRIQUES,
    Category,
    Challenge,
    FormField,
    Resource,
    SubmissionResult,
    SubmissionStatus,
    WebForm,
    WebPage,
)
from ..transport import STATIC_HOST, platform_url, sanitize_url
from .api import score_to_difficulty

_ALREADY_SOLVED_MESSAGES = (
    "already validated this challenge",
    "already solved this challenge",
    "déjà validé ce challenge",
    "déjà résolu ce challenge",
    "vous avez déjà les",
)


def attribute(tag: Tag, name: str, default: str = "") -> str:
    """Read a scalar HTML attribute rather than trusting malformed markup."""
    value = tag.get(name, default)
    if not isinstance(value, str):
        raise UnexpectedResponseError("Unexpected HTML attribute shape.")
    return value


def links(soup: BeautifulSoup | Tag, url: str) -> tuple[Resource, ...]:
    """Resolve ordinary links relative to the page, keeping their visible labels."""
    result = []
    for anchor in soup.select("a[href]"):
        target = sanitize_url(urljoin(url, attribute(anchor, "href").strip()))
        if urlsplit(target).scheme in {"https", "http"}:
            result.append(Resource(target, anchor.get_text(" ", strip=True)))
    return tuple(dict.fromkeys(result))


def _field(control: Tag) -> FormField:
    """Describe one real HTML control and its successful default value."""
    kind = attribute(control, "type", "text" if control.name == "input" else control.name).lower()
    value = attribute(control, "value")
    options = tuple(
        attribute(option, "value", option.get_text()) for option in control.select("option")
    )
    if control.name == "textarea":
        value = control.get_text()
    if control.name == "select":
        selected = control.select_one("option[selected]") or control.select_one("option")
        value = attribute(selected, "value", selected.get_text()) if selected else ""
    return FormField(
        attribute(control, "name"),
        kind,
        value,
        options,
        control.has_attr("required"),
        control.has_attr("checked"),
    )


def forms(soup: BeautifulSoup, url: str, base_url: str | None = None) -> tuple[WebForm, ...]:
    """Inventory named forms and fields, including transient SPIP hidden tokens."""
    result = []
    for index, form in enumerate(soup.select("form")):
        controls = form.select("input[name],textarea[name],select[name],button[name]")
        fields = tuple(_field(c) for c in controls if not c.has_attr("disabled"))
        action = next((f.value for f in fields if f.name == "formulaire_action"), "")
        name = action or attribute(form, "id", f"form-{index}")
        result.append(
            WebForm(
                url,
                urljoin(base_url or url, attribute(form, "action", url)),
                attribute(form, "method", "get").upper(),
                name,
                fields,
            )
        )
    return tuple(result)


def page(html: str, url: str) -> WebPage:
    """Parse a readable page and the exact forms currently offered by Root-Me."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    base_url = _base(soup, url)
    return WebPage(
        url,
        title,
        soup.get_text("\n", strip=True),
        links(soup, base_url),
        forms(soup, url, base_url),
        html,
    )


def _base(soup: BeautifulSoup, url: str) -> str:
    """Respect the site's observed base element when resolving relative links."""
    base = soup.select_one("base[href]")
    return urljoin(url, attribute(base, "href")) if base else url


_SLUG_CATEGORIES = (
    ("web-serveur", Category.WEB_SERVER),
    ("web-client", Category.WEB_CLIENT),
    ("app-script", Category.APP_SCRIPT),
    ("app-systeme", Category.APP_SYSTEM),
    ("cracking", Category.CRACKING),
    ("cryptanalyse", Category.CRYPTANALYSIS),
    ("forensic", Category.FORENSIC),
    ("programmation", Category.PROGRAMMING),
    ("realiste", Category.REALISTIC),
    ("reseau", Category.NETWORK),
    ("steganographie", Category.STEGANOGRAPHY),
)


def _page_category(url: str) -> Category | None:
    """Infer category from the verified challenge URL slug."""
    lower = url.lower()
    return next((cat for slug, cat in _SLUG_CATEGORIES if slug in lower), None)


def _page_solved(soup: BeautifulSoup) -> bool:
    """Detect if the challenge has already been validated by the current user."""
    container = soup.select_one(
        "#formulaire_validation_challenge, .formulaire_validation_challenge"
    )
    return bool(container and container.select_one(".reponse_formulaire_ok, .success"))


def _parse_id_and_score(score: Tag) -> tuple[int, int]:
    """Parse challenge id and point score from header elements."""
    identity = re.search(r"challenge-score-(\d+)", str(score.get("class", "")))
    points = re.search(r"\d+", score.get_text())
    if identity is None or points is None:
        raise UnexpectedResponseError("Missing challenge identifier or score.")
    return int(identity[1]), int(points[0])


def _page_authors_and_date(tile: Tag) -> tuple[tuple[str, ...], str | None]:
    """Extract authors and publication date from the challenge tile."""
    auth_header = tile.find(
        lambda t: (
            t.name in ["h4", "h5", "strong"]
            and any(k in t.get_text(strip=True).lower() for k in ("auteur", "author"))
        )
    )
    if not auth_header or not auth_header.parent:
        return (), None
    parent = auth_header.parent
    authors = tuple(
        a.get_text(strip=True)
        for a in parent.select("a[href]")
        if not attribute(a, "href").startswith("?") and "tri_co" not in attribute(a, "href")
    )
    match = re.search(r"(\d{1,2}\s+[a-zA-ZÀ-ÿ]+\s+\d{4})", parent.get_text())
    return authors, match[1].replace("\xa0", " ") if match else None


def _page_validations_count(tile: Tag) -> int | None:
    """Extract the total solve count from the validation popup link."""
    val_a = tile.select_one('a[href*="qui_a_valid"]')
    if not val_a:
        return None
    cleaned = val_a.get_text().replace("\xa0", "").replace(" ", "")
    match = re.search(r"(\d+)", cleaned)
    return int(match[1]) if match else None


def _is_challenge_host(resource: Resource) -> bool:
    """Detect whether a link targets Root-Me's hosted challenge servers."""
    host = urlsplit(resource.url).hostname or ""
    return host.endswith(".root-me.org") and host.startswith("challenge")


def _is_start_button(resource: Resource) -> bool:
    """Detect whether a link points to the interactive challenge instance."""
    is_target = any(k in resource.label.lower() for k in ("démarrer", "start", "accéder", "access"))
    return is_target or _is_challenge_host(resource)


def _page_instance_url(tile: Tag, base_url: str, cid: int) -> str | None:
    """Return the hosted instance behind the start button, which sits outside the description."""
    description = tile.select_one(f".challenge-descriptif-{cid}")
    described = set(links(description, base_url)) if description else set()
    return next(
        (
            resource.url
            for resource in links(tile, base_url)
            if _is_challenge_host(resource) and resource not in described
        ),
        None,
    )


def _page_links(
    tile: Tag, base_url: str, cid: int, statement: BeautifulSoup
) -> tuple[tuple[Resource, ...], tuple[Resource, ...]]:
    """Split challenge files served by Root-Me's static host from documentation links."""
    res: list[Resource] = list(links(statement, base_url))
    res_div = tile.select_one(f".challenge-ressources-{cid}")
    if res_div:
        res.extend(links(res_div, base_url))
    unique = tuple(dict.fromkeys(r for r in res if not _is_start_button(r)))
    files = tuple(r for r in unique if urlsplit(r.url).hostname == STATIC_HOST)
    return files, tuple(r for r in unique if r not in files)


def _page_statement(tile: Tag, cid: int) -> tuple[str, BeautifulSoup]:
    """Extract statement text and html container from challenge tile."""
    desc = tile.select_one(f".challenge-descriptif-{cid}")
    content = desc if desc is not None else tile.select_one(".t-body")
    if content is None:
        raise UnexpectedResponseError("Missing challenge statement container.")
    stmt = BeautifulSoup(str(content), "html.parser")
    for node in stmt.select("form,script,style,.formulaire_spip,.star-rating,.note_challenge"):
        node.decompose()
    return stmt.get_text("\n", strip=True), stmt


def challenge_page(document: WebPage, *, solved: bool | None = None) -> Challenge:
    """Read the observed challenge title, identifier, statement and resource links."""
    soup = BeautifulSoup(document.html, "html.parser")
    title, score = (
        soup.select_one('[class*="challenge-titre-"]'),
        soup.select_one('[class*="challenge-score-"]'),
    )
    if title is None or score is None:
        if any(f.name == "login" for f in document.forms):
            raise AuthenticationRequiredError("Challenge page requires a web session.")
        raise UnexpectedResponseError("Unsupported Root-Me challenge page.")
    tile = title.find_parent(class_="tile")
    if tile is None:
        raise UnexpectedResponseError("Missing challenge tile.")
    cid, score_val = _parse_id_and_score(score)
    stmt_text, stmt_soup = _page_statement(tile, cid)
    authors, date = _page_authors_and_date(tile)
    base_url = _base(soup, document.url)
    is_solved = solved if solved is not None else _page_solved(soup)
    category = _page_category(document.url)
    files, resources = _page_links(tile, base_url, cid, stmt_soup)
    return Challenge(
        id=cid,
        title=title.get_text(" ", strip=True),
        category=category,
        difficulty=score_to_difficulty(score_val),
        score=score_val,
        solved=is_solved,
        category_id=CATEGORY_RUBRIQUES.get(category) if category else None,
        url=document.url,
        statement_html=str(stmt_soup),
        statement=stmt_text,
        authors=authors,
        date=date,
        validations_count=_page_validations_count(tile),
        resources=resources,
        files=files,
        instance_url=_page_instance_url(tile, base_url, cid),
    )


def form_values(form: WebForm, updates: Mapping[str, str]) -> dict[str, str]:
    """Validate caller fields while preserving server-owned CSRF controls."""
    platform_url(form.page_url)
    platform_url(form.action)
    if urlsplit(form.action).hostname != "www.root-me.org" or form.method not in {"GET", "POST"}:
        raise ValueError("Unsupported website form action or method.")
    editable = {
        f.name: f for f in form.fields if f.kind not in {"hidden", "file", "submit", "button"}
    }
    submitters = {f.name for f in form.fields if f.kind in {"submit", "button"}}
    if not set(updates).issubset(editable.keys() | submitters):
        raise ValueError("Unknown, hidden or file form field.")
    for name, value in updates.items():
        field = editable.get(name)
        if field and field.options and value not in field.options:
            raise ValueError("Invalid select option.")
    result = {
        f.name: f.value
        for f in form.fields
        if f.kind not in {"submit", "button", "file"}
        and (f.kind not in {"checkbox", "radio"} or f.checked)
    }
    result.update(updates)
    return result


def submission_result(document: WebPage, answer: str) -> SubmissionResult:
    """Classify only explicit validation feedback and redact the supplied answer."""
    soup = BeautifulSoup(document.html, "html.parser")
    container = soup.select_one(
        "#formulaire_validation_challenge, .formulaire_validation_challenge"
    )
    if container is None:
        return SubmissionResult(SubmissionStatus.INDETERMINATE)
    success = container.select_one(".reponse_formulaire_ok, .success")
    rejection = container.select_one(".reponse_formulaire_erreur, .error")
    feedback = success or rejection
    if feedback:
        message = feedback.get_text(" ", strip=True).replace(answer, "[redacted]")
        if any(marker in message.lower() for marker in _ALREADY_SOLVED_MESSAGES):
            return SubmissionResult(SubmissionStatus.ALREADY_SOLVED, message)
    if success:
        return SubmissionResult(
            SubmissionStatus.ACCEPTED,
            success.get_text(" ", strip=True).replace(answer, "[redacted]"),
        )
    if rejection:
        message = rejection.get_text(" ", strip=True).replace(answer, "[redacted]")
        return SubmissionResult(SubmissionStatus.REJECTED, message)
    return SubmissionResult(SubmissionStatus.INDETERMINATE)
