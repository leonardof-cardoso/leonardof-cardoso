from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


README_PATH = Path("README.md")
START_MARKER = "<!-- dynamic:activity:start -->"
END_MARKER = "<!-- dynamic:activity:end -->"
USERNAME = os.getenv("GITHUB_USERNAME", "leonardof-cardoso")
API_ROOT = "https://api.github.com"
USER_AGENT = "readme-github-automation"


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def iso_to_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_date(value: str) -> str:
    return iso_to_date(value).strftime("%d/%m/%Y")


def relative_days(value: str) -> str:
    days = (datetime.now(timezone.utc) - iso_to_date(value)).days
    if days <= 0:
        return "hoje"
    if days == 1:
        return "ha 1 dia"
    return f"ha {days} dias"


def normalize_language(language: str | None) -> str:
    if not language:
        return "Outros"
    aliases = {
        "C#": "C#",
        "Jupyter Notebook": "Python",
        "Vue": "JavaScript",
    }
    return aliases.get(language, language)


def icon_for_language(language: str) -> str:
    icons = {
        "Python": "[PY]",
        "C#": "[C#]",
        "JavaScript": "[JS]",
        "TypeScript": "[TS]",
        "PHP": "[PHP]",
        "HTML": "[HTML]",
        "CSS": "[CSS]",
        "Shell": "[SH]",
        "Dockerfile": "[DKR]",
        "Go": "[GO]",
        "Java": "[JAVA]",
        "Outros": "[ETC]",
    }
    return icons.get(language, "[LANG]")


def recent_window() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=30)


def summarize_profile(repos: list[dict[str, Any]], recent_repos: list[dict[str, Any]]) -> list[str]:
    highlights: list[str] = []

    if recent_repos:
        latest = recent_repos[0]
        highlights.append(
            f"- Ultima movimentacao visivel em **{latest['name']}**, atualizado {relative_days(latest['updated_at'])}"
        )
        highlights.append(
            f"- **{len(recent_repos)} repositorios** receberam atividade publica nos ultimos 30 dias"
        )

    language_counts = Counter(
        normalize_language(repo.get("language")) for repo in recent_repos if repo.get("language")
    )
    if language_counts:
        common = ", ".join(name for name, _ in language_counts.most_common(3))
        highlights.append(f"- Stack mais presente na janela recente: **{common}**")

    if not highlights:
        highlights.append("- Sem atividade publica suficiente nos ultimos 30 dias para montar um resumo recente")

    return highlights[:3]


def build_focus(recent_repos: list[dict[str, Any]]) -> list[str]:
    language_counter: Counter[str] = Counter()
    topics_counter: Counter[str] = Counter()

    for repo in recent_repos:
        if repo.get("language"):
            language_counter[normalize_language(repo["language"])] += 1
        for topic in repo.get("topics", []):
            topics_counter[topic] += 1

    lines: list[str] = []
    if language_counter:
        top_langs = ", ".join(
            f"{icon_for_language(name)} {name}" for name, _ in language_counter.most_common(4)
        )
        lines.append(f"- Linguagens em evidenca nos ultimos 30 dias: **{top_langs}**")
    if topics_counter:
        top_topics = ", ".join(name for name, _ in topics_counter.most_common(4))
        lines.append(f"- Temas recorrentes nos projetos recentes: **{top_topics}**")
    lines.append(f"- Universo analisado: **{len(recent_repos)} repositorios** com atualizacao publica recente")
    return lines


def build_repo_lines(repos: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for repo in repos[:5]:
        name = repo["name"]
        url = repo["html_url"]
        language = normalize_language(repo.get("language"))
        updated_at = repo["updated_at"]
        description = (repo.get("description") or "Repositorio sem descricao publica.").strip()
        description = description.replace("\n", " ")
        lines.append(
            f"- [{name}]({url}) | {icon_for_language(language)} {language} | atualizado {relative_days(updated_at)}  \n"
            f"  {description}"
        )
    return lines


def event_phrase(event: dict[str, Any]) -> str | None:
    repo_name = event.get("repo", {}).get("name", "repositorio")
    event_type = event.get("type")
    payload = event.get("payload", {})

    if event_type == "PushEvent":
        commits = len(payload.get("commits", []))
        return f"Fez push com **{commits} commit(s)** em `{repo_name}`"
    if event_type == "PullRequestEvent":
        action = payload.get("action", "atualizou")
        return f"**{action.title()}** pull request em `{repo_name}`"
    if event_type == "IssuesEvent":
        action = payload.get("action", "atualizou")
        return f"**{action.title()}** issue em `{repo_name}`"
    if event_type == "CreateEvent":
        ref_type = payload.get("ref_type", "recurso")
        return f"Criou um novo **{ref_type}** em `{repo_name}`"
    if event_type == "WatchEvent":
        return f"Deu star em `{repo_name}`"
    if event_type == "ForkEvent":
        return f"Fez fork de `{repo_name}`"
    if event_type == "ReleaseEvent":
        return f"Publicou release em `{repo_name}`"
    return None


def build_event_lines(events: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for event in events:
        phrase = event_phrase(event)
        if not phrase:
            continue
        created_at = event.get("created_at")
        if not created_at:
            continue
        lines.append(f"- {phrase} ({format_date(created_at)})")
        if len(lines) == 5:
            break
    return lines or ["- Sem eventos publicos recentes disponiveis na API do GitHub."]


def build_language_chart(recent_repos: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[str]:
    repo_languages = {
        repo["name"]: normalize_language(repo.get("language"))
        for repo in recent_repos
        if repo.get("name")
    }
    language_counter: Counter[str] = Counter()
    cutoff = recent_window()

    for event in events:
        created_at = event.get("created_at")
        repo_full_name = event.get("repo", {}).get("name")
        if not created_at or not repo_full_name:
            continue

        event_date = iso_to_date(created_at)
        if event_date < cutoff:
            continue

        repo_name = repo_full_name.split("/")[-1]
        language = repo_languages.get(repo_name)
        if not language:
            continue

        weight = 1
        if event.get("type") == "PushEvent":
            weight += len(event.get("payload", {}).get("commits", []))
        language_counter[language] += weight

    if not language_counter:
        language_counter.update(
            normalize_language(repo.get("language"))
            for repo in recent_repos
            if repo.get("language")
        )

    if not language_counter:
        return ["```text", "Sem dados publicos suficientes nos ultimos 30 dias.", "```"]

    top_items = language_counter.most_common(5)
    max_value = top_items[0][1]
    lines = ["```text"]
    for language, value in top_items:
        bar_size = max(1, round((value / max_value) * 16))
        bar = "█" * bar_size
        label = f"{icon_for_language(language)} {language}"
        lines.append(f"{label:<18} {bar} {value}")
    lines.append("```")
    return lines


def render_dynamic_block(user: dict[str, Any], repos: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    profile_name = user.get("name") or USERNAME
    cutoff = recent_window()
    recent_repos = [repo for repo in repos if iso_to_date(repo["updated_at"]) >= cutoff]
    visible_repos = recent_repos[:5] if recent_repos else repos[:5]

    sections = [
        "### Radar tecnico",
        "",
        f"Leitura automatica do perfil publico de **{profile_name}** com foco em stack e atividade recente, sem metricas sociais e sem cards externos.",
        "",
        "#### Leitura rapida",
        *summarize_profile(repos, recent_repos),
        "",
        "#### Linguagens mais utilizadas nos ultimos 30 dias",
        *build_language_chart(recent_repos, events),
        "",
        "#### Repositorios em movimento",
        *build_repo_lines(visible_repos),
        "",
        "#### Ultimos eventos publicos",
        *build_event_lines(events),
        "",
        "#### Mapa tecnico",
        *build_focus(recent_repos),
        "",
        f"_Atualizado automaticamente em {generated_at}_",
    ]
    return "\n".join(sections)


def replace_block(content: str, new_block: str) -> str:
    if START_MARKER not in content or END_MARKER not in content:
        raise RuntimeError("Marcadores de automacao nao encontrados no README.")

    before, rest = content.split(START_MARKER, 1)
    _, after = rest.split(END_MARKER, 1)
    return f"{before}{START_MARKER}\n{new_block}\n{END_MARKER}{after}"


def main() -> None:
    try:
        user = fetch_json(f"{API_ROOT}/users/{USERNAME}")
        repos = fetch_json(f"{API_ROOT}/users/{USERNAME}/repos?per_page=100&sort=updated")
        events = fetch_json(f"{API_ROOT}/users/{USERNAME}/events/public?per_page=30")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Erro ao consultar API do GitHub: {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Erro de rede ao consultar API do GitHub: {exc.reason}") from exc

    content = README_PATH.read_text(encoding="utf-8")
    updated = replace_block(content, render_dynamic_block(user, repos, events))
    README_PATH.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
