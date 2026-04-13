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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
API_ROOT = "https://api.github.com"
USER_AGENT = "readme-github-automation"
PROGRAMMING_LANGUAGES = {
    "Python",
    "C#",
    "JavaScript",
    "TypeScript",
    "PHP",
    "Go",
    "Java",
}


def fetch_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    request = urllib.request.Request(
        url,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def iso_to_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
    normalized = aliases.get(language, language)
    return normalized if normalized in PROGRAMMING_LANGUAGES else "Outros"


def icon_for_language(language: str) -> str:
    icons = {
        "Python": "[PY]",
        "C#": "[C#]",
        "JavaScript": "[JS]",
        "TypeScript": "[TS]",
        "PHP": "[PHP]",
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


def filter_programming_repos(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [repo for repo in repos if normalize_language(repo.get("language")) != "Outros"]


def build_focus(recent_repos: list[dict[str, Any]]) -> list[str]:
    language_counter: Counter[str] = Counter()

    for repo in recent_repos:
        language = normalize_language(repo.get("language"))
        if language != "Outros":
            language_counter[language] += 1

    lines: list[str] = []
    if language_counter:
        top_langs = ", ".join(
            f"{icon_for_language(name)} {name}" for name, _ in language_counter.most_common(4)
        )
        lines.append(f"- Linguagens em evidenca nos ultimos 30 dias: **{top_langs}**")
    lines.append(f"- Universo analisado: **{sum(language_counter.values())} sinais tecnicos** em repositorios com linguagens fortes")
    return lines


def repo_score(repo: dict[str, Any]) -> int:
    score = 0
    name = repo.get("name", "").lower()
    description = (repo.get("description") or "").lower()
    language = normalize_language(repo.get("language"))

    if repo.get("archived"):
        score -= 50
    if repo.get("fork"):
        score -= 40
    if not description:
        score -= 8
    else:
        score += 12

    if language in {"Python", "C#", "TypeScript", "JavaScript", "PHP"}:
        score += 10

    keywords = [
        "api",
        "auth",
        "jwt",
        "saas",
        "dashboard",
        "discord",
        "chatbot",
        "bot",
        "manager",
        "task",
        "etl",
        "full",
    ]
    for keyword in keywords:
        if keyword in name or keyword in description:
            score += 6

    score += min(repo.get("stargazers_count", 0), 5)
    return score


def select_showcase_repos(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        repo
        for repo in filter_programming_repos(repos)
        if repo.get("name") != USERNAME and not repo.get("private", False)
    ]
    ranked = sorted(
        candidates,
        key=lambda repo: (repo_score(repo), iso_to_date(repo["updated_at"])),
        reverse=True,
    )
    return ranked[:4]


def build_repo_lines(repos: list[dict[str, Any]]) -> list[str]:
    if not repos:
        return ["- Nenhum repositorio elegivel para vitrine tecnica foi encontrado na leitura atual."]

    lines: list[str] = []
    for repo in repos:
        name = repo["name"]
        url = repo["html_url"]
        language = normalize_language(repo.get("language"))
        description = (repo.get("description") or "Repositorio sem descricao publica.").strip()
        description = description.replace("\n", " ")
        lines.append(
            f"- [{name}]({url}) | {icon_for_language(language)} {language}  \n"
            f"  {description}"
        )
    return lines


def build_language_chart(recent_repos: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[str]:
    repo_languages = {
        repo["name"]: normalize_language(repo.get("language"))
        for repo in recent_repos
        if repo.get("name") and normalize_language(repo.get("language")) != "Outros"
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
        if not language or language == "Outros":
            continue

        weight = 1
        if event.get("type") == "PushEvent":
            weight += len(event.get("payload", {}).get("commits", []))
        language_counter[language] += weight

    if not language_counter:
        language_counter.update(
            normalize_language(repo.get("language"))
            for repo in recent_repos
            if normalize_language(repo.get("language")) != "Outros"
        )

    if not language_counter:
        return ["```text", "Sem dados publicos suficientes nos ultimos 30 dias.", "```"]

    top_items = language_counter.most_common(5)
    max_value = top_items[0][1]
    lines = ["```text"]
    for language, value in top_items:
        bar_size = max(1, round((value / max_value) * 16))
        bar = "#" * bar_size
        label = f"{icon_for_language(language)} {language}"
        lines.append(f"{label:<18} {bar} {value}")
    lines.append("```")
    return lines


def render_dynamic_block(user: dict[str, Any], repos: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    profile_name = user.get("name") or USERNAME
    cutoff = recent_window()
    recent_repos = filter_programming_repos([repo for repo in repos if iso_to_date(repo["updated_at"]) >= cutoff])
    showcase_repos = select_showcase_repos(repos)

    sections = [
        "### Radar tecnico",
        "",
        f"Leitura automatica do perfil publico de **{profile_name}** com foco em stack real e projetos que funcionam como vitrine tecnica.",
        "",
        "#### Leitura rapida",
        *summarize_profile(repos, recent_repos),
        "",
        "#### Linguagens mais utilizadas nos ultimos 30 dias",
        *build_language_chart(recent_repos, events),
        "",
        "#### Repositorios em destaque",
        *build_repo_lines(showcase_repos),
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
