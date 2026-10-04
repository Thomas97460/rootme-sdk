"""Discover real website forms and parse challenge pages without guessed routes."""

import re
from collections.abc import Mapping
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from ..errors import AuthenticationRequiredError, UnexpectedResponseError
from ..models import (
    Challenge,
    FormField,
    Resource,
    SubmissionResult,
    SubmissionStatus,
    WebForm,
    WebPage,
)
from ..urls import platform_url

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
        target = urljoin(url, attribute(anchor, "href"))
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


def challenge_page(document: WebPage) -> Challenge:
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
    identity = re.search(r"challenge-score-(\d+)", str(score.get("class", "")))
    points = re.search(r"\d+", score.get_text())
    if identity is None or points is None:
        raise UnexpectedResponseError("Missing challenge identifier or score.")
    statement = _statement(title)
    return Challenge(
        int(identity[1]),
        title.get_text(" ", strip=True),
        int(points[0]),
        url=document.url,
        statement_html=str(statement),
        statement=statement.get_text("\n", strip=True),
        resources=links(statement, _base(soup, document.url)),
    )


def _statement(title: Tag) -> BeautifulSoup:
    """Keep the challenge body while removing forms and executable markup."""
    tile = title.find_parent(class_="tile")
    content = tile.select_one(".t-body") if tile else None
    if content is None:
        raise UnexpectedResponseError("Missing challenge statement container.")
    statement = BeautifulSoup(str(content), "html.parser")
    for node in statement.select("form,script,style,.formulaire_spip,.star-rating,.note_challenge"):
        node.decompose()
    return statement


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
