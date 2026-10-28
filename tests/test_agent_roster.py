"""Static guard: Claude Code project agents match docs/agents.md and keep the shared gates.

Standard library only. docs/agents.md is the source of truth for the roster table and the
gate block; every file in .claude/agents/ must agree with it.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".claude" / "agents"
DOC = ROOT / "docs" / "agents.md"
GATES = re.compile(r"<!-- sweet-seats-gates:start -->\n.*?<!-- sweet-seats-gates:end -->", re.S)
ROW = re.compile(r"^\| `([a-z0-9-]+)` \| (Auditor|Builder) \| [^|]+ \| ([^|]+) \|$", re.M)
AUDITOR_TOOLS = {"Read", "Grep", "Glob"}
FORBIDDEN_TOOLS = {"WebFetch", "WebSearch"}


def roster() -> dict[str, tuple[str, set[str]]]:
    rows = ROW.findall(DOC.read_text(encoding="utf-8"))
    return {name: (kind, {t.strip() for t in tools.split(",")}) for name, kind, tools in rows}


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}
    pairs = (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    return {key.strip(): value.strip().strip('"') for key, value in pairs}


class AgentRosterTest(unittest.TestCase):
    def setUp(self):
        self.roster = roster()
        self.gates = GATES.search(DOC.read_text(encoding="utf-8")).group(0)
        self.files = {p.stem: p.read_text(encoding="utf-8") for p in AGENTS.glob("*.md")}

    def test_roster_and_files_match(self):
        self.assertTrue(self.roster, "no roster rows parsed from docs/agents.md")
        self.assertEqual(set(self.roster), set(self.files))

    def test_frontmatter_name_and_description(self):
        for name, text in self.files.items():
            meta = frontmatter(text)
            self.assertEqual(meta.get("name"), name, name)
            self.assertTrue(meta.get("description"), name)

    def test_tools_match_roster_and_auditors_are_read_only(self):
        for name, (kind, tools) in self.roster.items():
            declared = {t.strip() for t in frontmatter(self.files[name]).get("tools", "").split(",")}
            self.assertEqual(declared, tools, name)
            self.assertFalse(declared & FORBIDDEN_TOOLS, name)
            if kind == "Auditor":
                self.assertEqual(declared, AUDITOR_TOOLS, name)

    def test_every_agent_carries_the_gate_block_verbatim(self):
        for name, text in self.files.items():
            self.assertEqual(GATES.findall(text), [self.gates], name)
            self.assertNotIn("{{GATES}}", text, name)


if __name__ == "__main__":
    unittest.main()
