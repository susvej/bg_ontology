"""Generate an interactive HTML ontology visualisation using vis.js Network."""

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>BGG Ontology — Interactive Graph</title>
<script src="https://unpkg.com/vis-network@9.1.9/dist/vis-network.min.js"></script>
<link  href="https://unpkg.com/vis-network@9.1.9/dist/dist/vis-network.min.css" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #1A1A2E; color: #CFD8DC; font-family: 'Segoe UI', sans-serif; display: flex; flex-direction: column; height: 100vh; }
  #header { padding: 10px 18px; background: #0D1117; border-bottom: 1px solid #30363D; display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
  #header h1 { font-size: 16px; font-weight: 700; color: #fff; }
  #header span { font-size: 12px; color: #8B949E; }
  .badge { font-size: 11px; padding: 3px 9px; border-radius: 12px; font-weight: 600; }
  #main { display: flex; flex: 1; overflow: hidden; }
  #graph { flex: 1; }
  #sidebar { width: 280px; background: #0D1117; border-left: 1px solid #30363D; padding: 14px; overflow-y: auto; flex-shrink: 0; font-size: 12px; }
  #sidebar h2 { font-size: 13px; font-weight: 700; color: #58A6FF; margin-bottom: 8px; }
  #sidebar .hint { color: #8B949E; margin-bottom: 12px; line-height: 1.5; }
  .prop-row { padding: 4px 0; border-bottom: 1px solid #21262D; display: flex; justify-content: space-between; align-items: baseline; }
  .prop-name { color: #79C0FF; font-family: monospace; font-size: 11px; }
  .prop-type { color: #A5D6FF; font-size: 10px; opacity: 0.7; }
  .prop-comment { color: #8B949E; font-size: 11px; margin-top: 3px; margin-bottom: 6px; line-height: 1.4; }
  #node-title { font-size: 15px; font-weight: 700; color: #fff; margin-bottom: 4px; }
  #node-comment { color: #8B949E; font-size: 12px; margin-bottom: 12px; line-height: 1.5; }
  .section-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8B949E; margin: 10px 0 4px; }
  #controls { padding: 8px 18px; background: #0D1117; border-top: 1px solid #30363D; display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap; align-items: center; }
  button { background: #21262D; color: #CFD8DC; border: 1px solid #30363D; border-radius: 6px; padding: 5px 12px; font-size: 12px; cursor: pointer; }
  button:hover { background: #30363D; }
  .legend { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-left: auto; }
  .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 4px; vertical-align: middle; }
  .legend-item { font-size: 11px; color: #8B949E; display: flex; align-items: center; }
</style>
</head>
<body>

<div id="header">
  <h1>BGG Ontology</h1>
  <span>Interactive class &amp; property graph</span>
  <span class="badge" style="background:#216BC2">10 classes</span>
  <span class="badge" style="background:#2E7D32">14 object properties</span>
  <span class="badge" style="background:#37474F">properties on all classes</span>
</div>

<div id="main">
  <div id="graph"></div>
  <div id="sidebar">
    <div class="hint">Click any class node to see its properties and description here.<br><br>
    <strong style="color:#CFD8DC">Tip:</strong> Drag nodes freely. Scroll to zoom. Double-click a node to expand / collapse its datatype properties as child nodes.</div>
  </div>
</div>

<div id="controls">
  <button onclick="network.fit()">Fit view</button>
  <button onclick="toggleAllAttrs()">Expand all attrs</button>
  <button onclick="collapseAllAttrs()">Collapse attrs</button>
  <button onclick="resetPhysics()">Re-layout</button>
  <div class="legend">
    <div class="legend-item"><span class="dot" style="background:#216BC2"></span>Game</div>
    <div class="legend-item"><span class="dot" style="background:#2E7D32"></span>Vocab classes</div>
    <div class="legend-item"><span class="dot" style="background:#6A1B9A"></span>Player / Opinion</div>
    <div class="legend-item"><span class="dot" style="background:#00695C"></span>Creator</div>
    <div class="legend-item"><span class="dot" style="background:#1565C0"></span>Publisher</div>
    <div class="legend-item"><span class="dot" style="background:#E65100"></span>trenj:Theme</div>
    <div class="legend-item"><span style="border-bottom:2px dashed #FF8A65;width:18px;display:inline-block;margin-right:4px;vertical-align:middle"></span>Patch predicate</div>
  </div>
</div>

<script>
const CLASS_NODES = [
  { id:"Game",          label:"bgg:Game",          color:{background:"#216BC2",border:"#90CAF9"}, group:"game",    shape:"box",
    comment:"A board game listed on BoardGameGeek, carrying descriptive properties such as name, player count, play time, and aggregate community ratings." },
  { id:"Category",      label:"bgg:Category",      color:{background:"#2E7D32",border:"#A5D6A7"}, group:"vocab",   shape:"box",
    comment:"A thematic grouping for board games as defined by BoardGameGeek (e.g. Fantasy, Economic, Card Game)." },
  { id:"Mechanic",      label:"bgg:Mechanic",      color:{background:"#2E7D32",border:"#A5D6A7"}, group:"vocab",   shape:"box",
    comment:"A game-play mechanism or rule pattern as defined by BoardGameGeek (e.g. Auction/Bidding, Worker Placement, Dice Rolling)." },
  { id:"Publisher",     label:"bgg:Publisher",     color:{background:"#1565C0",border:"#90CAF9"}, group:"pub",     shape:"box",
    comment:"A company or individual that publishes board games." },
  { id:"Creator",       label:"bgg:Creator",       color:{background:"#00695C",border:"#80CBC4"}, group:"creator", shape:"box",
    comment:"A person who designed or created a board game. Names stored as rdfs:label." },
  { id:"Size",          label:"bgg:Size",           color:{background:"#2E7D32",border:"#A5D6A7"}, group:"vocab",   shape:"box",
    comment:"A physical size category for a game box (e.g. small, medium, large)." },
  { id:"MentalLoad",    label:"bgg:MentalLoad",    color:{background:"#2E7D32",border:"#A5D6A7"}, group:"vocab",   shape:"box",
    comment:"An ordered enumeration of perceived cognitive difficulty: easy, moderate, or difficult." },
  { id:"Theme",         label:"trenj:Theme",       color:{background:"#E65100",border:"#FFAB40"}, group:"trenj",   shape:"box",
    comment:"A thematic tag sourced from the threnjen Kaggle dataset. Distinct from bgg:Category." },
  { id:"Player",        label:"bgg:Player",        color:{background:"#6A1B9A",border:"#CE93D8"}, group:"agent",   shape:"box",
    comment:"A person who plays board games; may own games and record personal opinions on them." },
  { id:"PlayerOpinion", label:"bgg:PlayerOpinion", color:{background:"#6A1B9A",border:"#CE93D8"}, group:"agent",   shape:"box",
    comment:"Reifies a player-game relationship to carry subjective properties: personal rating, mental load perception, and free-text comment." },
];

const OBJ_EDGES = [
  { from:"Game",         to:"Category",      label:"hasCategory",        color:{color:"#90CAF9"} },
  { from:"Game",         to:"Mechanic",      label:"hasMechanic",        color:{color:"#90CAF9"} },
  { from:"Game",         to:"Creator",       label:"hasCreator",         color:{color:"#90CAF9"} },
  { from:"Game",         to:"Publisher",     label:"hasPublisher",       color:{color:"#90CAF9"} },
  { from:"Game",         to:"Size",          label:"hasSize",            color:{color:"#90CAF9"} },
  { from:"Game",         to:"Theme",         label:"trenj:hasTheme",     color:{color:"#FFAB40"} },
  { from:"Player",       to:"Game",          label:"hasOwnershipOf",     color:{color:"#CE93D8"} },
  { from:"Player",       to:"Category",      label:"likesCategory",      color:{color:"#CE93D8"} },
  { from:"Player",       to:"Mechanic",      label:"likesMechanic",      color:{color:"#CE93D8"} },
  { from:"PlayerOpinion",to:"Player",        label:"hasOpinionHolder",   color:{color:"#CE93D8"} },
  { from:"PlayerOpinion",to:"Game",          label:"hasOpinionOf",       color:{color:"#CE93D8"} },
  { from:"PlayerOpinion",to:"MentalLoad",    label:"hasMentalLoad",      color:{color:"#CE93D8"} },
  { from:"Game",         to:"Game",          label:"reimplements",       color:{color:"#FF8A65"}, dashes:true, smooth:{type:"curvedCCW",roundness:0.5} },
  { from:"Game",         to:"Game",          label:"isExpansionOf",      color:{color:"#FF8A65"}, dashes:true, smooth:{type:"curvedCW", roundness:0.5} },
  // Inverse properties (hidden by default, toggle via sidebar)
  { from:"Category",     to:"Game",          label:"isCategoryOf",       color:{color:"#546E7A"}, hidden:true },
  { from:"Mechanic",     to:"Game",          label:"isMechanicOf",       color:{color:"#546E7A"}, hidden:true },
  { from:"Game",         to:"Player",        label:"isOwnedBy",          color:{color:"#546E7A"}, hidden:true },
];

const DATATYPE_PROPS = {
  "Game": [
    { name:"bgg:hasName",              type:"xsd:string",  comment:"Name as listed on BGG. (owl:DatatypeProperty)" },
    { name:"bgg:hasID",                type:"xsd:int",     comment:"Unique BGG numeric identifier. (owl:DatatypeProperty)" },
    { name:"bgg:hasYearPublished",     type:"xsd:int",     comment:"Year first published. (owl:DatatypeProperty)" },
    { name:"bgg:hasGeekRating",        type:"xsd:double",  comment:"BGG Geek Rating, adjusted for vote count. (owl:DatatypeProperty)" },
    { name:"bgg:hasRating",            type:"xsd:double",  comment:"Average community rating (1–10). (owl:DatatypeProperty)" },
    { name:"bgg:hasComplexity",        type:"xsd:double",  comment:"Average weight/complexity (1 light – 5 heavy). (owl:DatatypeProperty)" },
    { name:"bgg:hasMinPlayers",        type:"xsd:int",     comment:"Minimum number of players. (owl:DatatypeProperty)" },
    { name:"bgg:hasMaxPlayers",        type:"xsd:int",     comment:"Maximum number of players. (owl:DatatypeProperty)" },
    { name:"bgg:hasBestNumPlayers",    type:"xsd:int",     comment:"Community-voted best player count. (owl:DatatypeProperty)" },
    { name:"bgg:hasMinGameTime",       type:"xsd:int",     comment:"Minimum play time in minutes. (owl:DatatypeProperty)" },
    { name:"bgg:hasMaxGameTime",       type:"xsd:int",     comment:"Maximum play time in minutes. (owl:DatatypeProperty)" },
    { name:"bgg:hasMinRecAge",         type:"xsd:int",     comment:"Minimum recommended age. (owl:DatatypeProperty)" },
    { name:"bgg:hasMaxRecAge",         type:"xsd:int",     comment:"Maximum recommended age. (owl:DatatypeProperty)" },
    { name:"bgg:hasNumRatings",        type:"xsd:int",     comment:"Total number of BGG community ratings. (owl:DatatypeProperty)" },
    { name:"bgg:hasDescription",       type:"xsd:string",  comment:"Human-readable description from BGG. (owl:DatatypeProperty)" },
    { name:"bgg:isExpansion",          type:"xsd:boolean", comment:"True if this is an expansion, not a standalone base game. (owl:DatatypeProperty)" },
    { name:"bgg:isFullyEnriched",      type:"xsd:boolean", comment:"True if mechanics/categories/creators/publishers are all loaded. (owl:DatatypeProperty)" },
    { name:"bgg:ratingFromTime",       type:"xsd:int",     comment:"Year the rating data was collected. (owl:DatatypeProperty)" },
    { name:"bgg:hasURL",               type:"xsd:anyURI",  comment:"BGG web page URL for this game. (owl:ObjectProperty, no range declared)" },
    { name:"bgg:hasThumbnail",         type:"xsd:anyURI",  comment:"Thumbnail image URL from BGG. (owl:ObjectProperty, no range declared)" },
  ],
  "PlayerOpinion": [
    { name:"bgg:hasPlayerRatingOpinion", type:"xsd:decimal", comment:"Personal rating (1–10) by the opinion holder. (owl:DatatypeProperty)" },
    { name:"bgg:hasComment",             type:"xsd:string",  comment:"Free-text comment written by the player. (owl:DatatypeProperty)" },
  ],
  "Category": [
    { name:"rdfs:label",     type:"xsd:string (lang-tagged)", comment:"The category name, e.g. 'Fantasy', 'Economic', 'Card Game'. Used as the primary identifier for instances." },
    { name:"skos:altLabel",  type:"xsd:string (repeatable)",  comment:"Alternative search terms, e.g. Bluffing → 'deception', 'lying', 'social deduction'. Enables fuzzy/natural-language matching in SPARQL." },
  ],
  "Mechanic": [
    { name:"rdfs:label",     type:"xsd:string (lang-tagged)", comment:"The mechanic name, e.g. 'Worker Placement', 'Deck Building', 'Auction/Bidding'." },
    { name:"skos:altLabel",  type:"xsd:string (repeatable)",  comment:"Alternative names for the mechanic, e.g. 'Drafting' also matches 'Card Drafting'." },
  ],
  "Creator": [
    { name:"rdfs:label",     type:"xsd:string (lang-tagged)", comment:"The designer's full name, e.g. 'Uwe Rosenberg'. No bgg:hasName — names are stored directly on the instance via rdfs:label." },
  ],
  "Publisher": [
    { name:"rdfs:label",     type:"xsd:string (lang-tagged)", comment:"The publisher's name, e.g. 'Stonemaier Games'. No bgg:hasName — stored directly as rdfs:label." },
  ],
  "Size": [
    { name:"rdfs:label",     type:"xsd:string (lang-tagged)", comment:"The size label: 'small', 'medium', or 'large'. Controlled vocabulary — instances defined in T-BOX." },
  ],
  "MentalLoad": [
    { name:"rdfs:label",     type:"xsd:string (lang-tagged)", comment:"The difficulty label: 'easy', 'moderate', or 'difficult'. Ordered enumeration defined in T-BOX." },
  ],
  "Theme": [
    { name:"rdfs:label",     type:"xsd:string (lang-tagged)", comment:"Theme name from the threnjen dataset, e.g. 'Pirates', 'Space Exploration'. Parallel to bgg:Category but from a different source." },
    { name:"skos:altLabel",  type:"xsd:string (repeatable)",  comment:"Search aliases for this theme. Some instances are shared with bgg:Category (rdf:type on both classes)." },
  ],
  "Player": [
    { name:"rdfs:label",     type:"xsd:string (lang-tagged)", comment:"The player's full name, e.g. 'Susanne Vejdemo'. No bgg:hasName — stored as rdfs:label directly on the instance." },
  ],
};

// ── Build vis datasets ─────────────────────────────────────────────
let nodeData = new vis.DataSet();
let edgeData = new vis.DataSet();

let nodeIdCounter = 1000;
let attrNodeIds = {};   // classId -> [attrNodeId, ...]
let attrExpanded = {};  // classId -> bool

CLASS_NODES.forEach(n => {
  nodeData.add({
    ...n,
    font: { color:"#FFFFFF", size:13, bold:true },
    widthConstraint: { minimum:120 },
    margin: 8,
  });
  attrExpanded[n.id] = false;
});

OBJ_EDGES.forEach((e, i) => {
  edgeData.add({
    id: "obj_" + i,
    from: e.from, to: e.to,
    label: e.label,
    color: e.color,
    dashes: e.dashes || false,
    hidden: e.hidden || false,
    arrows: { to: { enabled:true, scaleFactor:0.6 } },
    smooth: e.smooth || { type:"dynamic" },
    font: { color:"#CFD8DC", size:10, align:"middle",
            background:"#1A1A2E", strokeWidth:0 },
    width: 1.5,
  });
});

// ── vis.js Network ─────────────────────────────────────────────────
const container = document.getElementById("graph");
const options = {
  physics: {
    solver: "forceAtlas2Based",
    forceAtlas2Based: { gravitationalConstant:-80, centralGravity:0.005,
                        springLength:160, springConstant:0.06, damping:0.5 },
    stabilization: { iterations:150 },
  },
  interaction: { hover:true, tooltipDelay:200 },
  nodes: { borderWidth:2, borderWidthSelected:3, shadow:{ enabled:true, size:6, color:"rgba(0,0,0,0.5)" } },
  edges: { selectionWidth:2.5 },
  layout: { improvedLayout:true },
};
const network = new vis.Network(container, { nodes:nodeData, edges:edgeData }, options);

// ── Sidebar: show node info on click ──────────────────────────────
const sidebar = document.getElementById("sidebar");

function showNodeInfo(nodeId) {
  const classNode = CLASS_NODES.find(n => n.id === nodeId);
  if (!classNode) return;

  const attrs = DATATYPE_PROPS[nodeId] || [];
  const objOut = OBJ_EDGES.filter(e => e.from === nodeId && !e.hidden);
  const objIn  = OBJ_EDGES.filter(e => e.to   === nodeId && !e.hidden);

  let html = `<div id="node-title">${classNode.label}</div>`;
  html += `<div id="node-comment">${classNode.comment}</div>`;

  if (attrs.length) {
    html += `<div class="section-label">Datatype Properties (${attrs.length})</div>`;
    attrs.forEach(p => {
      html += `<div class="prop-row"><span class="prop-name">${p.name}</span><span class="prop-type">${p.type}</span></div>`;
      html += `<div class="prop-comment">${p.comment}</div>`;
    });
  }

  if (objOut.length) {
    html += `<div class="section-label">Outgoing Object Properties</div>`;
    objOut.forEach(e => {
      html += `<div class="prop-row"><span class="prop-name">${e.label}</span><span class="prop-type">→ ${e.to}</span></div>`;
    });
  }
  if (objIn.length) {
    html += `<div class="section-label">Incoming Object Properties</div>`;
    objIn.forEach(e => {
      html += `<div class="prop-row"><span class="prop-name">${e.label}</span><span class="prop-type">← ${e.from}</span></div>`;
    });
  }

  sidebar.innerHTML = html;
}

// ── Double-click: expand / collapse datatype attr nodes ───────────
function expandAttrs(nodeId) {
  const attrs = DATATYPE_PROPS[nodeId];
  if (!attrs) return;

  if (attrExpanded[nodeId]) {
    // collapse
    const ids = attrNodeIds[nodeId] || [];
    nodeData.remove(ids.map(x => x.nodeId));
    edgeData.remove(ids.map(x => x.edgeId));
    attrNodeIds[nodeId] = [];
    attrExpanded[nodeId] = false;
  } else {
    // expand
    const ids = [];
    attrs.forEach(p => {
      const nid = "attr_" + (nodeIdCounter++);
      const eid = "attre_" + nodeIdCounter;
      nodeData.add({
        id: nid,
        label: p.name + "\n" + p.type,
        shape: "ellipse",
        color: { background:"#21262D", border:"#546E7A" },
        font: { color:"#A5D6FF", size:9 },
        mass: 0.3,
      });
      edgeData.add({
        id: eid,
        from: nodeId, to: nid,
        dashes: [4,3],
        color: { color:"#546E7A" },
        arrows: { to:{ enabled:true, scaleFactor:0.4 }},
        font: { size:0 },
        width: 1,
      });
      ids.push({ nodeId:nid, edgeId:eid });
    });
    attrNodeIds[nodeId] = ids;
    attrExpanded[nodeId] = true;
  }
}

network.on("click", params => {
  if (params.nodes.length === 1) showNodeInfo(params.nodes[0]);
});
network.on("doubleClick", params => {
  if (params.nodes.length === 1) expandAttrs(params.nodes[0]);
});

function toggleAllAttrs() {
  CLASS_NODES.forEach(n => { if (!attrExpanded[n.id]) expandAttrs(n.id); });
}
function collapseAllAttrs() {
  CLASS_NODES.forEach(n => { if (attrExpanded[n.id]) expandAttrs(n.id); });
}
function resetPhysics() {
  network.setOptions({ physics:{ enabled:true } });
  setTimeout(() => network.setOptions({ physics:{ enabled:false } }), 3000);
}

// Disable physics after stabilisation so dragged nodes stay put
network.on("stabilizationIterationsDone", () => {
  network.setOptions({ physics:{ enabled:false } });
});
</script>
</body>
</html>
"""

with open("../index.html", "w", encoding="utf-8") as f:
    f.write(HTML)
print("Saved: ../index.html")
