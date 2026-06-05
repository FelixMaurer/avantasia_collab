from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple
import tempfile
import html
import json

import networkx as nx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
try:
    from pyvis.network import Network
except Exception:
    Network = None

APP_DIR = Path(__file__).resolve().parent
NODES_PATH = APP_DIR / "nodes.csv"
EDGES_PATH = APP_DIR / "edges.csv"

TYPE_COLORS = {
    "project": "#F4B942",
    "artist": "#7FB3FF",
    "band": "#9BE28F",
}
TYPE_SHAPES = {
    "project": "star",
    "artist": "dot",
    "band": "box",
}

st.set_page_config(
    page_title="Avantasia Collaboration Network",
    page_icon="🎸",
    layout="wide",
)

st.markdown(
    """
    <style>
    .detail-card {
        border: 1px solid rgba(49, 51, 63, 0.18);
        border-radius: 12px;
        padding: 0.85rem 0.95rem;
        margin: 0.55rem 0;
        background: rgba(250,250,250,0.85);
        overflow-wrap: anywhere;
        word-break: normal;
        line-height: 1.42;
    }
    .detail-card h3 { margin: 0 0 0.25rem 0; font-size: 1.08rem; }
    .detail-card p { margin: 0.45rem 0 0 0; white-space: normal; }
    .detail-subtitle { color: #666; font-size: 0.86rem; margin-bottom: 0.35rem; }
    </style>
    """,
    unsafe_allow_html=True,
)




def clean_text(value: object) -> str:
    """Return readable text: remove accidental HTML tags and unescape entities."""
    text = html.unescape(str(value or "")).replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    # Strip a small set of formatting tags if they were pasted into the CSV.
    for tag in ["b", "strong", "i", "em", "p", "div", "span", "ul", "ol", "li"]:
        text = text.replace(f"<{tag}>", "").replace(f"</{tag}>", "")
    return " ".join(text.split()) if "\n" not in text else "\n".join(" ".join(line.split()) for line in text.splitlines())


def html_block(title: str, rows: List[Tuple[str, object]]) -> str:
    body = [f"<div class='tip-title'>{html.escape(clean_text(title))}</div>"]
    for label, value in rows:
        text = clean_text(value)
        if text:
            body.append(
                "<div class='tip-row'>"
                f"<span class='tip-label'>{html.escape(label)}:</span> "
                f"<span>{html.escape(text)}</span>"
                "</div>"
            )
    return "<div class='graph-tip'>" + "".join(body) + "</div>"


def detail_card(title: str, subtitle: str, description: str, extra: List[Tuple[str, object]] | None = None) -> None:
    rows = ""
    for label, value in extra or []:
        text = clean_text(value)
        if text:
            rows += f"<p><b>{html.escape(label)}:</b> {html.escape(text)}</p>"
    st.markdown(
        f"""
        <div class="detail-card">
            <h3>{html.escape(clean_text(title))}</h3>
            <div class="detail-subtitle">{html.escape(clean_text(subtitle))}</div>
            <p>{html.escape(clean_text(description))}</p>
            {rows}
        </div>
        """,
        unsafe_allow_html=True,
    )


def relation_cards(rels: pd.DataFrame, nodes: pd.DataFrame, node_id: str | None = None, max_cards: int = 40) -> None:
    label_by_id = dict(zip(nodes["id"], nodes["label"]))
    if rels.empty:
        st.write("No relationships in the current dataset.")
        return
    for _, row in rels.head(max_cards).iterrows():
        source = label_by_id.get(row["source"], row["source"])
        target = label_by_id.get(row["target"], row["target"])
        if node_id:
            other = row["target"] if row["source"] == node_id else row["source"]
            title = label_by_id.get(other, other)
        else:
            title = f"{source} ↔ {target}"
        detail_card(
            title=title,
            subtitle=f"Relation: {row['relation']} · Weight: {row['weight']}",
            description=row["description"],
        )
    if len(rels) > max_cards:
        st.caption(f"Showing first {max_cards} of {len(rels)} relationships.")

def require_file(path: Path, columns: List[str]) -> None:
    if not path.exists():
        st.error(
            f"Missing file: `{path.name}`. Put `{path.name}` in the same GitHub folder as `app.py`. "
            "This version deliberately does not use a data folder."
        )
        st.stop()
    preview = pd.read_csv(path, nrows=1)
    missing = [c for c in columns if c not in preview.columns]
    if missing:
        st.error(f"`{path.name}` is missing required columns: {', '.join(missing)}")
        st.stop()


@st.cache_data(show_spinner=False)
def load_tables() -> Tuple[pd.DataFrame, pd.DataFrame]:
    require_file(NODES_PATH, ["id", "label", "type", "description", "aliases", "source_note"])
    require_file(EDGES_PATH, ["source", "target", "relation", "description", "weight"])
    nodes = pd.read_csv(NODES_PATH).fillna("")
    edges = pd.read_csv(EDGES_PATH).fillna("")
    nodes["id"] = nodes["id"].astype(str).str.strip()
    nodes["label"] = nodes["label"].astype(str).str.strip()
    nodes["type"] = nodes["type"].astype(str).str.strip().str.lower()
    edges["source"] = edges["source"].astype(str).str.strip()
    edges["target"] = edges["target"].astype(str).str.strip()
    edges["relation"] = edges["relation"].astype(str).str.strip()
    edges["description"] = edges["description"].astype(str).str.strip()
    edges["weight"] = pd.to_numeric(edges["weight"], errors="coerce").fillna(1)
    return nodes, edges


def validate_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> List[str]:
    node_ids = set(nodes["id"])
    problems = []
    for i, row in edges.iterrows():
        if row["source"] not in node_ids:
            problems.append(f"Row {i + 2} in edges.csv has unknown source `{row['source']}`")
        if row["target"] not in node_ids:
            problems.append(f"Row {i + 2} in edges.csv has unknown target `{row['target']}`")
    dupes = nodes[nodes["id"].duplicated()]["id"].tolist()
    if dupes:
        problems.append("Duplicate node IDs: " + ", ".join(sorted(set(dupes))))
    return problems


def build_networkx(nodes: pd.DataFrame, edges: pd.DataFrame) -> nx.Graph:
    g = nx.Graph()
    for _, row in nodes.iterrows():
        g.add_node(row["id"], **row.to_dict())
    for idx, row in edges.iterrows():
        if row["source"] in g and row["target"] in g:
            g.add_edge(row["source"], row["target"], edge_id=f"edge_{idx}", **row.to_dict())
    return g


def ego_filter(g: nx.Graph, focus_id: str, depth: int) -> set[str]:
    if not focus_id or focus_id == "__all__":
        return set(g.nodes)
    if focus_id not in g:
        return set(g.nodes)
    lengths = nx.single_source_shortest_path_length(g, focus_id, cutoff=depth)
    return set(lengths.keys())


def text_match_filter(nodes: pd.DataFrame, edges: pd.DataFrame, query: str) -> set[str]:
    if not query.strip():
        return set(nodes["id"])
    q = query.strip().lower()
    matched_nodes = set(
        nodes[
            nodes[["id", "label", "type", "description", "aliases", "source_note"]]
            .astype(str)
            .agg(" ".join, axis=1)
            .str.lower()
            .str.contains(q, regex=False)
        ]["id"]
    )
    matched_edges = edges[
        edges[["source", "target", "relation", "description"]]
        .astype(str)
        .agg(" ".join, axis=1)
        .str.lower()
        .str.contains(q, regex=False)
    ]
    matched_nodes |= set(matched_edges["source"]) | set(matched_edges["target"])
    return matched_nodes


def make_visible_tables(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    visible_ids: set[str],
    min_weight: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    ndf = nodes[nodes["id"].isin(visible_ids)].copy()
    edf = edges[
        edges["source"].isin(visible_ids)
        & edges["target"].isin(visible_ids)
        & (edges["weight"] >= min_weight)
    ].copy()
    return ndf, edf


def render_pyvis(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    physics: bool,
    hierarchical: bool,
    height: int = 780,
) -> None:
    if Network is None:
        st.error("Missing dependency `pyvis`. Make sure requirements.txt contains `pyvis>=0.3.2`.")
        st.stop()

    net = Network(height=f"{height}px", width="100%", bgcolor="#ffffff", font_color="#222222", directed=False)
    net.toggle_physics(physics)
    if hierarchical:
        net.set_options("""{
          "layout": {"hierarchical": {"enabled": true, "sortMethod": "hubsize"}},
          "physics": {"enabled": false},
          "interaction": {"hover": true, "navigationButtons": true, "keyboard": true}
        }""")
    else:
        net.set_options("""{
          "physics": {
            "enabled": true,
            "barnesHut": {
              "gravitationalConstant": -8000,
              "centralGravity": 0.25,
              "springLength": 160,
              "springConstant": 0.035,
              "damping": 0.25,
              "avoidOverlap": 0.45
            },
            "stabilization": {"iterations": 250}
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 80,
            "navigationButtons": true,
            "keyboard": true,
            "multiselect": true
          }
        }""")

    degree = pd.concat([edges["source"], edges["target"]]).value_counts().to_dict() if not edges.empty else {}
    for _, row in nodes.iterrows():
        node_type = row["type"] if row["type"] in TYPE_COLORS else "project"
        size = 18 + min(34, int(degree.get(row["id"], 0)) * 3)
        if row["id"] == "avantasia":
            size = 55
        title = html_block(
            row["label"],
            [
                ("Type", row["type"]),
                ("Description", row["description"]),
                ("Aliases", row["aliases"]),
                ("Note", row["source_note"]),
            ],
        )
        net.add_node(
            row["id"],
            label=row["label"],
            title=title,
            color=TYPE_COLORS.get(node_type, "#CCCCCC"),
            shape=TYPE_SHAPES.get(node_type, "dot"),
            size=size,
            borderWidth=3 if row["id"] == "avantasia" else 1,
        )

    for _, row in edges.iterrows():
        source_label = nodes.loc[nodes["id"] == row["source"], "label"].iloc[0] if row["source"] in set(nodes["id"]) else row["source"]
        target_label = nodes.loc[nodes["id"] == row["target"], "label"].iloc[0] if row["target"] in set(nodes["id"]) else row["target"]
        title = html_block(
            f"{source_label} ↔ {target_label}",
            [("Relation", row["relation"]), ("Description", row["description"])],
        )
        net.add_edge(
            row["source"],
            row["target"],
            title=title,
            label=row["relation"],
            value=max(1, float(row["weight"])),
            width=max(1, min(8, float(row["weight"]) / 1.5)),
            smooth={"type": "dynamic"},
        )

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        net.save_graph(f.name)
        html = Path(f.name).read_text(encoding="utf-8")

    html = html.replace(
        "</head>",
        """
        <style>
          .vis-tooltip {
            max-width: 460px !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
            word-break: normal !important;
            line-height: 1.35 !important;
            font-family: Arial, sans-serif !important;
            font-size: 13px !important;
            padding: 10px 12px !important;
            border-radius: 8px !important;
            box-shadow: 0 4px 18px rgba(0,0,0,.14) !important;
          }
          .graph-tip { max-width: 440px; white-space: normal; overflow-wrap: anywhere; }
          .tip-title { font-weight: 700; font-size: 15px; margin-bottom: 7px; }
          .tip-row { margin-top: 5px; }
          .tip-label { font-weight: 700; }
          #selection-panel {
            position: fixed; right: 12px; bottom: 12px; width: 390px; max-height: 270px;
            overflow-y: auto; background: rgba(255,255,255,.96); border: 1px solid #ddd;
            border-radius: 10px; padding: 10px 12px; font-family: Arial, sans-serif;
            font-size: 13px; line-height: 1.38; z-index: 9999; box-shadow: 0 4px 18px rgba(0,0,0,.12);
            overflow-wrap: anywhere;
          }
          #selection-panel h3 { margin: 0 0 4px 0; font-size: 15px; }
          #selection-panel p { margin: 6px 0; }
          #selection-panel .muted { color: #666; font-size: 12px; }
        </style>
        </head>
        """,
    )
    html = html.replace(
        "</body>",
        """
        <div style="position:fixed;left:12px;bottom:12px;background:rgba(255,255,255,.92);border:1px solid #ddd;border-radius:8px;padding:8px 10px;font-family:Arial;font-size:12px;max-width:430px;z-index:9998;">
          Hover for wrapped tooltips. Use the detail selectors beside the graph for stable full text.
        </div>
        <div id="selection-panel">
          <h3>Selection</h3>
          <p class="muted">Click or hover a node/edge. Long descriptions are also shown in the Streamlit detail panel.</p>
        </div>
        <script>
          function readableTitle(raw) {
            if (!raw) return "";
            const div = document.createElement('div');
            div.innerHTML = raw;
            return div.innerText || div.textContent || "";
          }
          function writePanel(kind, id) {
            const panel = document.getElementById('selection-panel');
            if (!panel || typeof network === 'undefined') return;
            let item = null;
            if (kind === 'node') item = nodes.get(id);
            if (kind === 'edge') item = edges.get(id);
            if (!item) return;
            const title = kind === 'node' ? (item.label || id) : (item.label || 'Relationship');
            const text = readableTitle(item.title || '');
            panel.innerHTML = '<h3>' + title + '</h3>' +
              '<p class="muted">' + kind + '</p>' +
              '<p>' + text.replace(/\n/g, '<br>') + '</p>';
          }
          if (typeof network !== 'undefined') {
            network.on('click', function(params) {
              if (params.nodes && params.nodes.length) writePanel('node', params.nodes[0]);
              else if (params.edges && params.edges.length) writePanel('edge', params.edges[0]);
            });
            network.on('hoverNode', function(params) { writePanel('node', params.node); });
            network.on('hoverEdge', function(params) { writePanel('edge', params.edge); });
          }
        </script>
        </body>
        """,
    )
    components.html(html, height=height + 30, scrolling=False)

def node_details(node_id: str, nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    row = nodes[nodes["id"] == node_id]
    if row.empty:
        st.info("Click a node in the graph, or choose one from the dropdown below.")
        return
    r = row.iloc[0]
    detail_card(
        title=r["label"],
        subtitle=f"Type: {r['type']} · ID: {r['id']}",
        description=r["description"],
        extra=[("Aliases", r["aliases"]), ("Note", r["source_note"])],
    )

    rels = edges[(edges["source"] == node_id) | (edges["target"] == node_id)].copy()
    st.markdown("**Relationships**")
    relation_cards(
        rels.sort_values(["weight", "relation"], ascending=[False, True]),
        nodes,
        node_id=node_id,
        max_cards=30,
    )

def edge_details(edge_key: str, edges: pd.DataFrame, nodes: pd.DataFrame) -> None:
    if not edge_key:
        return
    idx = int(edge_key.split("__", 1)[0])
    if idx not in edges.index:
        return
    row = edges.loc[idx]
    label_by_id = dict(zip(nodes["id"], nodes["label"]))
    detail_card(
        title=f"{label_by_id.get(row['source'], row['source'])} ↔ {label_by_id.get(row['target'], row['target'])}",
        subtitle=f"Relation: {row['relation']} · Weight: {row['weight']}",
        description=row["description"],
    )


nodes_df, edges_df = load_tables()
problems = validate_graph(nodes_df, edges_df)
if problems:
    st.error("Graph validation problems found:")
    for p in problems[:20]:
        st.write("- " + p)
    if len(problems) > 20:
        st.write(f"...and {len(problems) - 20} more.")
    st.stop()

g = build_networkx(nodes_df, edges_df)

st.title("Avantasia Collaboration Network")
st.caption("Interactive physics map of Avantasia guests, bands, side projects, and cross-links. Files are flat: app.py, nodes.csv, edges.csv.")

with st.sidebar:
    st.header("Graph controls")
    node_options = {"All nodes": "__all__"}
    node_options.update({f"{r.label} [{r.type}]": r.id for r in nodes_df.sort_values("label").itertuples()})
    default_focus_label = next(k for k, v in node_options.items() if v == "avantasia")
    focus_label = st.selectbox("Focus / ego network", list(node_options.keys()), index=list(node_options.keys()).index(default_focus_label))
    depth = st.slider("Connection depth from focus", 1, 4, 2)
    min_weight = st.slider("Minimum relationship weight", 1.0, 10.0, 1.0, 0.5)
    selected_types = st.multiselect(
        "Node types",
        sorted(nodes_df["type"].unique()),
        default=sorted(nodes_df["type"].unique()),
    )
    query = st.text_input("Search labels/descriptions", "")
    physics = st.toggle("Physics / spring layout", value=True)
    hierarchical = st.toggle("Hierarchical layout", value=False)
    st.divider()
    st.write(f"Nodes in dataset: **{len(nodes_df)}**")
    st.write(f"Edges in dataset: **{len(edges_df)}**")

focus_ids = ego_filter(g, node_options[focus_label], depth)
query_ids = text_match_filter(nodes_df, edges_df, query)
type_ids = set(nodes_df[nodes_df["type"].isin(selected_types)]["id"])
visible = focus_ids & query_ids & type_ids

visible_nodes, visible_edges = make_visible_tables(
    nodes_df, edges_df, visible, min_weight
)

left, right = st.columns([2.1, 1], gap="large")

with left:
    st.write(f"Showing **{len(visible_nodes)}** nodes and **{len(visible_edges)}** relationships.")
    render_pyvis(visible_nodes, visible_edges, physics=physics, hierarchical=hierarchical, height=780)

with right:
    st.header("Details")
    st.caption("Hover/click in the graph for quick tooltips; use these selectors for stable full descriptions on Streamlit Cloud.")
    selected_node = "avantasia"
    visible_node_labels = {
        f"{r.label} [{r.type}]": r.id for r in visible_nodes.sort_values("label").itertuples()
    }
    if selected_node in set(visible_nodes["id"]):
        default_label = next((k for k, v in visible_node_labels.items() if v == selected_node), None)
    else:
        default_label = next(iter(visible_node_labels), None) if visible_node_labels else None
    if default_label:
        chosen_label = st.selectbox(
            "Node details",
            list(visible_node_labels.keys()),
            index=list(visible_node_labels.keys()).index(default_label),
        )
        node_details(visible_node_labels[chosen_label], nodes_df, edges_df)

    st.divider()
    if not visible_edges.empty:
        label_by_id = dict(zip(nodes_df["id"], nodes_df["label"]))
        edge_options: Dict[str, str] = {}
        for idx, row in visible_edges.iterrows():
            label = f"{label_by_id.get(row['source'], row['source'])} ↔ {label_by_id.get(row['target'], row['target'])} — {row['relation']}"
            edge_options[label] = f"{idx}__{row['source']}__{row['target']}"
        chosen_edge = st.selectbox("Relationship details", list(edge_options.keys()))
        edge_details(edge_options[chosen_edge], edges_df, nodes_df)

st.divider()
with st.expander("Edit / extend the dataset"):
    st.write(
        "To add more connections, edit `nodes.csv` and `edges.csv` in the repo root. "
        "Every edge source/target must exist as an `id` in `nodes.csv`."
    )
    st.code(
        "nodes.csv: id,label,type,description,aliases,source_note\n"
        "edges.csv: source,target,relation,description,weight",
        language="text",
    )
    st.download_button("Download current nodes.csv", nodes_df.to_csv(index=False).encode("utf-8"), "nodes.csv", "text/csv")
    st.download_button("Download current edges.csv", edges_df.to_csv(index=False).encode("utf-8"), "edges.csv", "text/csv")
