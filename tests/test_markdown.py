from app.markdown import render_answer
from app.models import Evidence


def references():
    return [Evidence(evidence_id="test", source_type="internal", source_name="wiki",
                     title="SVE", url="/compiler/pages/concepts/sve", text="source", citation=1)]


def test_markdown_blocks_and_citations():
    result = render_answer("## 标题\n\n**重点** [1] [[SVE]] [[未知]]\n\n- 步骤\n\n"
                           "|项目|结果|\n|---|---|\n|测试|成功|\n\n```python\nprint('[1]')\n```", references())
    assert "<h2>标题</h2>" in result
    assert "<strong>重点</strong>" in result
    assert "<ul>" in result and "<table>" in result
    assert result.count('href="/compiler/pages/concepts/sve"') == 2
    assert "[[未知]]" in result
    assert "<pre><code" in result and "print('[1]')" in result


def test_untrusted_html_and_dangerous_links_are_not_executable():
    result = render_answer('<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n'
                           '[bad](javascript:alert(1)) [bad](data:text/html,test)\n\n'
                           '![tracking](https://example.com/pixel)')
    assert "<script" not in result and "<img" not in result
    assert 'href="javascript:' not in result and 'href="data:' not in result
    assert "&lt;script&gt;" in result


def test_citations_do_not_rewrite_code_or_existing_links():
    result = render_answer('`[1] [[SVE]]`\n\n[1](https://example.com)\n\n'
                           '[see [1]](https://example.com)', references())
    assert "<code>[1] [[SVE]]</code>" in result
    assert '/compiler/pages/' not in result
    assert result.count("<a ") == 2
