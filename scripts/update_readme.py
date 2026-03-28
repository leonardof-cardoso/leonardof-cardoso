from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
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


def summarize_profile(user: dict[str, Any], repos: list[dict[str, Any]]) -> list[str]:
    highlights: list[str] = []

    public_repos = user.get("public_repos", 0)
    followers = user.get("followers", 0)
    company = user.get("company")
    location = user.get("location")

    if company:
        highlights.append(f"- Atua publicamente no ecossistema GitHub com base profissional ligada a **{company}**")
    if location:
        highlights.append(f"- Perfil localizado em **{location}**, com projetos e atividade publica centralizados em desenvolvimento e integracao")

    highlights.append(f"- Mantem **{public_repos} repositorios publicos** e uma rede de **{followers} seguidores** no GitHub")

    top_languages = [repo["language"] for repo in repos if repo.get("language")]
    language_counts = Counter(top_languages)
    if language_counts:
        common = ", ".join(name for name, _ in language_counts.most_common(3))
        highlights.append(f"- Tecnologias mais recorrentes entre os repositorios recentes: **{common}**")

    return highlights[:4]


def build_focus(repos: list[dict[str, Any]]) -> list[str]:
    language_counter: Counter[str] = Counter()
    topics_counter: Counter[str] = Counter()
    archived_count = 0

    for repo in repos[:20]:
        if repo.get("language"):
            language_counter[repo["language"]] += 1
        for topic in repo.get("topics", []):
            topics_counter[topic] += 1
        if repo.get("archived"):
            archived_count += 1

    lines: list[str] = []
    if language_counter:
        top_langs = ", ".join(name for name, _ in language_counter.most_common(4))
        lines.append(f"- Linguagens em evidenca nos repositorios recentes: **{top_langs}**")
    if topics_counter:
        top_topics = ", ".join(name for name, _ in topics_counter.most_common(4))
        lines.append(f"- Temas recorrentes nos projetos: **{top_topics}**")
    active_count = max(min(len(repos), 20) - archived_count, 0)
    lines.append(f"- Universo analisado: **{active_count} repositorios ativos** entre os mais recentes")
    return lines


def build_repo_lines(repos: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for repo in repos[:5]:
        name = repo["name"]
        url = repo["html_url"]
        language = repo.get("language") or "stack variada"
        updated_at = repo["updated_at"]
        stars = repo.get("stargazers_count", 0)
        description = (repo.get("description") or "Repositorio sem descricao publica.").strip()
        description = description.replace("\n", " ")
        lines.append(
            f"- [{name}]({url}) | {language} | atualizado {relative_days(updated_at)} | {stars} estrelas  \n"
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


def render_dynamic_block(user: dict[str, Any], repos: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    profile_name = user.get("name") or USERNAME

    sections = [
        "### Radar de atividade",
        "",
        f"Leitura automatica do perfil publico de **{profile_name}** para mostrar sinais reais de atividade, sem depender de cards externos.",
        "",
        "#### Leitura rapida",
        *summarize_profile(user, repos),
        "",
        "#### Repositorios em foco",
        *build_repo_lines(repos),
        "",
        "#### Eventos publicos recentes",
        *build_event_lines(events),
        "",
        "#### Mapa tecnico",
        *build_focus(repos),
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
