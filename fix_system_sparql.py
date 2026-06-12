"""Fix SYSTEM_SPARQL cell in bgg_sparql_qa.ipynb:

1. Strip "Theme " prefix from all quoted vocabulary labels (theme vocab list
   and class-description examples now use clean labels like "Steampunk").
2. Remove the stale note telling the LLM to include the "Theme " prefix.
3. Fix "SpiesSecret Agents" -> "Spies / Secret Agents" in category vocab.
"""
import json
import re

NB_FILE = "bgg_sparql_qa.ipynb"
CELL_ID = "c4034405"


def fix_source(text: str) -> str:
    # 1. Strip "Theme " prefix from every quoted string that starts with it.
    #    e.g.  "Theme Steampunk"  ->  "Steampunk"
    #          "Theme African Americans"  ->  "African Americans"
    text = re.sub(r'"Theme ([^"]+)"', lambda m: '"' + m.group(1) + '"', text)

    # 2. Remove the stale note about the Theme prefix (match the whole line).
    text = re.sub(
        r'Note: threnjen-specific themes use a[^\n]+\n?',
        '',
        text,
    )

    # 3. Fix residual category vocab label.
    text = text.replace('"SpiesSecret Agents"', '"Spies / Secret Agents"')

    return text


def main() -> None:
    with open(NB_FILE, encoding="utf-8-sig") as f:
        nb = json.load(f)

    updated = False
    for cell in nb["cells"]:
        if cell.get("id") != CELL_ID:
            continue
        src = cell["source"]
        text = src if isinstance(src, str) else "".join(src)
        fixed = fix_source(text)
        if fixed == text:
            print("No changes needed.")
        else:
            lines = fixed.split("\n")
            cell["source"] = [l + "\n" for l in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
            print(f"Cell {CELL_ID} updated.")
        updated = True
        break

    if not updated:
        raise RuntimeError(f"Cell {CELL_ID} not found")

    with open(NB_FILE, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print("Saved.")


if __name__ == "__main__":
    main()
