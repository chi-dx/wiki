"""Render model output without allowing raw HTML or executable links."""
import re

from markdown_it import MarkdownIt


def render_answer(answer, evidence=()):
    markdown = MarkdownIt("js-default").disable("image")
    references = {}
    for item in evidence:
        references[f"[{item.citation}]"] = item.url
        references[f"[[{item.title}]]"] = item.url

    def citation(state, silent):
        if silent or state.linkLevel or state.src[state.pos:state.pos + 1] != "[":
            return False
        match = re.match(r"\[\[[^\]\n]+\]\]|\[\d+\]", state.src[state.pos:])
        if not match:
            return False
        label = match.group()
        end = state.pos + len(label)
        url = references.get(label)
        if not url or state.src[end:end + 1] in ("(", "["):
            return False
        url = markdown.normalizeLink(url)
        if not markdown.validateLink(url):
            return False
        if not silent:
            token = state.push("link_open", "a", 1)
            token.attrs = {"href": url, "class": "citation"}
            token = state.push("text", "", 0)
            token.content = label[2:-2] if label.startswith("[[") else label
            state.push("link_close", "a", -1)
        state.pos = end
        return True

    markdown.inline.ruler.before("link", "citation", citation)
    return markdown.render(answer)
