"""Generate a class-and-edges diagram of the BGG ontology."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np

fig, ax = plt.subplots(figsize=(20, 14))
ax.set_xlim(0, 20); ax.set_ylim(0, 14)
ax.axis("off")
fig.patch.set_facecolor("#1A1A2E")
ax.set_facecolor("#1A1A2E")

# ── Colours ───────────────────────────────────────────────────────
C_GAME    = "#216BC2"
C_VOCAB   = "#2E7D32"   # controlled vocab: Category/Mechanic/Size/MentalLoad
C_AGENT   = "#6A1B9A"   # Player, PlayerOpinion
C_CREATOR = "#00695C"
C_TRENJ   = "#E65100"   # trenj:Theme
C_PUBLISH = "#1565C0"
C_EDGE    = "#90CAF9"
C_EDGE2   = "#FFB74D"   # Game→Game edges
C_DASH    = "#FF8A65"   # undeclared patch predicates
WHITE     = "#FFFFFF"
LIGHT     = "#CFD8DC"

# ── Node positions  (x, y) ────────────────────────────────────────
NODES = {
    "Game":          (10.0, 7.5),
    "Category":      ( 4.0, 11.0),
    "Mechanic":      ( 4.0,  8.0),
    "Creator":       ( 4.0,  5.0),
    "Publisher":     ( 4.0,  2.5),
    "Size":          (10.0, 11.8),
    "MentalLoad":    (16.5,  5.5),
    "Theme":         (16.5, 11.0),
    "Player":        ( 7.5,  2.5),
    "PlayerOpinion": (13.5,  2.5),
}

NODE_COLOR = {
    "Game":          C_GAME,
    "Category":      C_VOCAB,
    "Mechanic":      C_VOCAB,
    "Creator":       C_CREATOR,
    "Publisher":     C_PUBLISH,
    "Size":          C_VOCAB,
    "MentalLoad":    C_VOCAB,
    "Theme":         C_TRENJ,
    "Player":        C_AGENT,
    "PlayerOpinion": C_AGENT,
}

NODE_PREFIX = {
    "Theme": "trenj:",
}

NODE_ATTRS = {
    "Game": [
        "hasName  xsd:string",
        "hasID  xsd:int",
        "hasYearPublished  xsd:int",
        "hasGeekRating  xsd:double",
        "hasRating  xsd:double",
        "hasComplexity  xsd:double",
        "hasMinPlayers / hasMaxPlayers  xsd:int",
        "hasBestNumPlayers  xsd:int",
        "hasMinGameTime / hasMaxGameTime  xsd:int",
        "hasMinRecAge / hasMaxRecAge  xsd:int",
        "hasNumRatings  xsd:int",
        "hasDescription  xsd:string",
        "isExpansion  xsd:boolean",
        "isFullyEnriched  xsd:boolean",
        "ratingFromTime  xsd:int",
    ],
    "PlayerOpinion": [
        "hasPlayerRatingOpinion  xsd:decimal",
        "hasComment  xsd:string",
    ],
}

# ── Draw node boxes ───────────────────────────────────────────────
BOX_W = 2.6; BOX_H = 0.55
ATTR_H = 0.22
node_boxes = {}

for name, (cx, cy) in NODES.items():
    color = NODE_COLOR[name]
    prefix = NODE_PREFIX.get(name, "bgg:")
    attrs = NODE_ATTRS.get(name, [])
    total_h = BOX_H + (len(attrs) * ATTR_H if attrs else 0)

    # Header box
    hdr = FancyBboxPatch((cx - BOX_W/2, cy - BOX_H/2),
                          BOX_W, BOX_H,
                          boxstyle="round,pad=0.04",
                          facecolor=color, edgecolor=WHITE, linewidth=1.5, zorder=3)
    ax.add_patch(hdr)
    label = f"{prefix}{name}" if prefix != "bgg:" else f"bgg:{name}"
    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=10, fontweight="bold", color=WHITE, zorder=4)

    # Attribute rows (below header)
    if attrs:
        attr_bg = FancyBboxPatch((cx - BOX_W/2, cy - BOX_H/2 - len(attrs)*ATTR_H),
                                  BOX_W, len(attrs)*ATTR_H,
                                  boxstyle="round,pad=0.02",
                                  facecolor="#0D1B2A", edgecolor=color, linewidth=1.0, zorder=3)
        ax.add_patch(attr_bg)
        for j, attr in enumerate(attrs):
            ay = cy - BOX_H/2 - (j + 0.5) * ATTR_H
            ax.text(cx - BOX_W/2 + 0.08, ay, f"  {attr}",
                    ha="left", va="center", fontsize=6.2, color=LIGHT,
                    fontfamily="monospace", zorder=4)

    node_boxes[name] = (cx, cy)

# ── Arrow helper ──────────────────────────────────────────────────
def arrow(src, dst, label, color=C_EDGE, dashed=False,
          offset_src=(0,0), offset_dst=(0,0), label_offset=(0,0),
          rad=0.0):
    sx, sy = NODES[src][0]+offset_src[0], NODES[src][1]+offset_src[1]
    dx, dy = NODES[dst][0]+offset_dst[0], NODES[dst][1]+offset_dst[1]

    style = f"arc3,rad={rad}"
    ls = (0,(4,3)) if dashed else "-"
    arr = FancyArrowPatch((sx, sy), (dx, dy),
                          arrowstyle="-|>",
                          connectionstyle=style,
                          color=color,
                          linewidth=1.4 if not dashed else 1.1,
                          linestyle=ls,
                          mutation_scale=14, zorder=2)
    ax.add_patch(arr)

    # label midpoint
    mx = (sx + dx) / 2 + label_offset[0]
    my = (sy + dy) / 2 + label_offset[1]
    ax.text(mx, my, label, ha="center", va="center",
            fontsize=7.5, color=color, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="#1A1A2E",
                      edgecolor="none", alpha=0.85), zorder=5)

# ── Object-property edges ─────────────────────────────────────────
arrow("Game", "Category",   "hasCategory",   offset_dst=(BOX_W/2, 0), label_offset=(-0.3, 0.3))
arrow("Game", "Mechanic",   "hasMechanic",   offset_dst=(BOX_W/2, 0), label_offset=(-0.2, 0.2))
arrow("Game", "Creator",    "hasCreator",    offset_dst=(BOX_W/2, 0), label_offset=(-0.3,-0.2))
arrow("Game", "Publisher",  "hasPublisher",  offset_dst=(BOX_W/2, 0), label_offset=(-0.3,-0.3))
arrow("Game", "Size",       "hasSize",       offset_src=(0, BOX_H/2), offset_dst=(0,-BOX_H/2), label_offset=(0.8, 0.1))
arrow("Game", "Theme",      "trenj:hasTheme", offset_dst=(-BOX_W/2, 0), label_offset=(1.0, 0.2))
arrow("Player", "Game",     "hasOwnershipOf", offset_src=(BOX_W/2, 0), offset_dst=(-0.4,-BOX_H/2-0.5), label_offset=(0, -0.28))
arrow("Player", "Category", "likesCategory",  offset_src=(0, BOX_H/2), offset_dst=(BOX_W/2,-BOX_H/2), label_offset=(-0.6, 0.5), rad=0.2)
arrow("Player", "Mechanic", "likesMechanic",  offset_src=(0, BOX_H/2), offset_dst=(BOX_W/2, 0),        label_offset=(-0.5, 0.6), rad=0.3)
arrow("PlayerOpinion", "Player",      "hasOpinionHolder", offset_src=(-BOX_W/2,0), offset_dst=(BOX_W/2,0), label_offset=(0,-0.30))
arrow("PlayerOpinion", "Game",        "hasOpinionOf",     offset_src=(0, BOX_H/2), offset_dst=(0.8,-BOX_H/2-0.5), label_offset=(0.7,-0.3))
arrow("PlayerOpinion", "MentalLoad",  "hasMentalLoad",    offset_src=(BOX_W/2, 0), offset_dst=(-BOX_W/2,-BOX_H/2), label_offset=(0.9, 0.3))

# ── Game→Game edges (patch predicates, dashed) ────────────────────
arrow("Game", "Game", "reimplements",  color=C_DASH, dashed=True,
      offset_src=(BOX_W/2+0.1, 0.25), offset_dst=(BOX_W/2+0.1,-0.25),
      label_offset=(2.2, 0.0), rad=-0.8)
arrow("Game", "Game", "isExpansionOf", color=C_DASH, dashed=True,
      offset_src=(BOX_W/2+0.1, 0.0), offset_dst=(BOX_W/2+0.1,-0.50),
      label_offset=(2.5,-0.5), rad=-1.1)

# ── Legend ────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(color=C_GAME,    label="Game"),
    mpatches.Patch(color=C_VOCAB,   label="Controlled vocabulary\n(Category/Mechanic/Size/MentalLoad)"),
    mpatches.Patch(color=C_AGENT,   label="Player / PlayerOpinion"),
    mpatches.Patch(color=C_CREATOR, label="Creator"),
    mpatches.Patch(color=C_PUBLISH, label="Publisher"),
    mpatches.Patch(color=C_TRENJ,   label="trenj:Theme"),
    mpatches.Patch(color=C_EDGE,    label="Declared ObjectProperty (bgg:)"),
    mpatches.Patch(color=C_DASH,    label="Undeclared predicate (patch data)"),
]
leg = ax.legend(handles=legend_items, loc="lower right",
                fontsize=8, framealpha=0.85,
                facecolor="#0D1B2A", edgecolor="#445566", labelcolor=WHITE)

ax.set_title("BGG Ontology — Classes & Object Properties",
             fontsize=16, fontweight="bold", color=WHITE, pad=10)

plt.tight_layout()
plt.savefig("bgg_ontology_diagram.png", dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print("Saved: bgg_ontology_diagram.png")
