"""Generate a class-and-edges diagram of the BGG ontology."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# ── Canvas ────────────────────────────────────────────────────────
# figsize=(16,11) at dpi=150 → 2400×1650px.
# GitHub displays README images ~900px wide (2.67× downscale),
# so 18pt text renders as ~14px — readable without zooming.
fig, ax = plt.subplots(figsize=(16, 11))
ax.set_xlim(0, 16); ax.set_ylim(0, 11)
ax.axis("off")
fig.patch.set_facecolor("#1A1A2E")
ax.set_facecolor("#1A1A2E")

# ── Colours ───────────────────────────────────────────────────────
C_GAME    = "#216BC2"
C_VOCAB   = "#2E7D32"
C_AGENT   = "#6A1B9A"
C_CREATOR = "#00695C"
C_TRENJ   = "#E65100"
C_PUBLISH = "#1565C0"
C_EDGE    = "#90CAF9"
C_DASH    = "#FF8A65"
WHITE     = "#FFFFFF"
LIGHT     = "#CFD8DC"

# ── Node positions ────────────────────────────────────────────────
NODES = {
    "Game":          ( 8.5, 6.5),
    "Category":      ( 3.0, 9.2),
    "Mechanic":      ( 3.0, 6.5),
    "Creator":       ( 3.0, 4.0),
    "Publisher":     ( 3.0, 1.8),
    "Size":          ( 8.5, 10.0),
    "MentalLoad":    (14.0, 4.5),
    "Theme":         (14.0, 9.2),
    "Player":        ( 7.0, 1.2),
    "PlayerOpinion": (12.0, 1.2),
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

NODE_PREFIX = {"Theme": "trenj:"}

# ── Draw node boxes ───────────────────────────────────────────────
BOX_W = 2.6; BOX_H = 0.72

for name, (cx, cy) in NODES.items():
    color = NODE_COLOR[name]
    prefix = NODE_PREFIX.get(name, "bgg:")
    box = FancyBboxPatch((cx - BOX_W/2, cy - BOX_H/2),
                          BOX_W, BOX_H,
                          boxstyle="round,pad=0.06",
                          facecolor=color, edgecolor=WHITE, linewidth=1.8, zorder=3)
    ax.add_patch(box)
    label = f"{prefix}{name}"
    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=14, fontweight="bold", color=WHITE, zorder=4)

# ── Arrow helper ──────────────────────────────────────────────────
def arrow(src, dst, label, color=C_EDGE, dashed=False,
          offset_src=(0, 0), offset_dst=(0, 0), label_offset=(0, 0), rad=0.0):
    sx = NODES[src][0] + offset_src[0]
    sy = NODES[src][1] + offset_src[1]
    dx = NODES[dst][0] + offset_dst[0]
    dy = NODES[dst][1] + offset_dst[1]
    arr = FancyArrowPatch(
        (sx, sy), (dx, dy),
        arrowstyle="-|>",
        connectionstyle=f"arc3,rad={rad}",
        color=color,
        linewidth=1.6 if not dashed else 1.2,
        linestyle="-" if not dashed else (0, (4, 3)),
        mutation_scale=16, zorder=2)
    ax.add_patch(arr)
    mx = (sx + dx) / 2 + label_offset[0]
    my = (sy + dy) / 2 + label_offset[1]
    ax.text(mx, my, label, ha="center", va="center",
            fontsize=10, color=color, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#1A1A2E",
                      edgecolor="none", alpha=0.9), zorder=5)

# ── Edges ─────────────────────────────────────────────────────────
H = BOX_H / 2; W = BOX_W / 2

arrow("Game", "Category",   "hasCategory",    offset_dst=(W, 0),   label_offset=(-0.2, 0.35))
arrow("Game", "Mechanic",   "hasMechanic",    offset_dst=(W, 0),   label_offset=(-0.1, 0.25))
arrow("Game", "Creator",    "hasCreator",     offset_dst=(W, 0),   label_offset=(-0.2,-0.25))
arrow("Game", "Publisher",  "hasPublisher",   offset_dst=(W, 0),   label_offset=(-0.3,-0.35))
arrow("Game", "Size",       "hasSize",        offset_src=(0, H),   offset_dst=(0, -H), label_offset=(0.7, 0.1))
arrow("Game", "Theme",      "trenj:hasTheme", offset_dst=(-W, 0),  label_offset=(0.9, 0.25))
arrow("PlayerOpinion", "MentalLoad", "hasMentalLoad", offset_src=(W, 0), offset_dst=(-W, 0), label_offset=(0.5, 0.3))

arrow("Player", "Game",      "hasOwnershipOf",  offset_src=(W, 0),   offset_dst=(-0.3, -H-0.4), label_offset=(0.1,-0.3))
arrow("Player", "Category",  "likesCategory",   offset_src=(0, H),   offset_dst=(W, -H),         label_offset=(-0.5, 0.5), rad=0.25)
arrow("Player", "Mechanic",  "likesMechanic",   offset_src=(-W+0.2, H), offset_dst=(W, 0),       label_offset=(-0.9, 0.45), rad=0.3)

arrow("PlayerOpinion", "Player", "hasOpinionHolder", offset_src=(-W, 0),  offset_dst=(W, 0),          label_offset=(0,-0.32))
arrow("PlayerOpinion", "Game",   "hasOpinionOf",     offset_src=(0, H),   offset_dst=(0.9, -H-0.4),   label_offset=(0.7,-0.3))

arrow("Game", "Game", "reimplements",  color=C_DASH, dashed=True,
      offset_src=(W+0.1,  0.25), offset_dst=(W+0.1, -0.25),
      label_offset=(2.0, 0.0), rad=-0.8)
arrow("Game", "Game", "isExpansionOf", color=C_DASH, dashed=True,
      offset_src=(W+0.1,  0.0),  offset_dst=(W+0.1, -0.50),
      label_offset=(2.3,-0.5), rad=-1.1)

ax.set_title("BGG Ontology — Classes & Object Properties",
             fontsize=20, fontweight="bold", color=WHITE, pad=12)

plt.savefig("bgg_ontology_diagram.png", dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print("Saved: bgg_ontology_diagram.png")
