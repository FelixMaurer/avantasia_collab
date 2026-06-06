from pathlib import Path
import html
import re
import tempfile

import pandas as pd
import streamlit as st
from pyvis.network import Network
import streamlit.components.v1 as components

APP_DIR = Path(__file__).resolve().parent
NODES_PATH = APP_DIR / "nodes.csv"
EDGES_PATH = APP_DIR / "edges.csv"

st.set_page_config(page_title="Avantasia Collaboration Network", layout="wide")

TYPE_COLORS = {
    "project": "#d99000",
    "artist": "#6aa6ff",
    "band": "#8bd17c",
}
TYPE_SHAPES = {
    "project": "star",
    "artist": "dot",
    "band": "box",
}


def clean_text(value: object) -> str:
    """Make text safe and readable for pyvis tooltips and Streamlit cards.

    Important: pyvis/vis.js treats `title` as HTML. If HTML tags are passed,
    they are rendered or displayed depending on browser/mobile behavior. We
    therefore strip any tags and never intentionally pass HTML into tooltips.
    """
    if value is None:
        return ""
    text = str(value)
    text = html.unescape(text)
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@st.cache_data
def load_tables():
    missing = [p.name for p in [NODES_PATH, EDGES_PATH] if not p.exists()]
    if missing:
        st.error("Missing file(s): " + ", ".join(missing) + ". Keep app.py, nodes.csv and edges.csv in the same GitHub folder.")
        st.stop()
    nodes = pd.read_csv(NODES_PATH).fillna("")
    edges = pd.read_csv(EDGES_PATH).fillna("")

    required_nodes = {"id", "label", "type", "description"}
    required_edges = {"source", "target", "relation", "description"}
    if not required_nodes.issubset(nodes.columns):
        st.error(f"nodes.csv must contain columns: {', '.join(sorted(required_nodes))}")
        st.stop()
    if not required_edges.issubset(edges.columns):
        st.error(f"edges.csv must contain columns: {', '.join(sorted(required_edges))}")
        st.stop()

    for col in nodes.columns:
        nodes[col] = nodes[col].map(clean_text)
    for col in edges.columns:
        edges[col] = edges[col].map(clean_text)

    # Auto-add placeholder nodes if an edge points to a node not listed yet.
    known = set(nodes["id"])
    endpoints = set(edges["source"]).union(edges["target"])
    missing_ids = sorted(endpoints - known)
    if missing_ids:
        extra = pd.DataFrame({
            "id": missing_ids,
            "label": [x.replace("_", " ").title() for x in missing_ids],
            "type": ["project"] * len(missing_ids),
            "description": ["Placeholder node auto-created because it appears in edges.csv but not nodes.csv." for _ in missing_ids],
        })
        nodes = pd.concat([nodes, extra], ignore_index=True)
    return nodes, edges


def tooltip_lines(title: str, rows: list[tuple[str, str]]) -> str:
    parts = [clean_text(title), ""]
    for key, value in rows:
        if clean_text(value):
            parts.append(f"{clean_text(key)}: {clean_text(value)}")
    # Plain text only. New lines are safe in vis.js title popups.
    return "\n".join(parts)


def build_network(nodes_df: pd.DataFrame, edges_df: pd.DataFrame, show_edge_labels: bool, physics_strength: int):
    net = Network(height="760px", width="100%", bgcolor="#ffffff", font_color="#222222", directed=False)
    net.barnes_hut(gravity=-physics_strength, central_gravity=0.18, spring_length=160, spring_strength=0.035, damping=0.35, overlap=0.4)

    degree = pd.concat([edges_df["source"], edges_df["target"]]).value_counts().to_dict()

    for _, row in nodes_df.iterrows():
        node_id = row["id"]
        ntype = row.get("type", "project")
        size = 20 + min(35, degree.get(node_id, 0) * 2)
        if node_id == "avantasia":
            size = 55
        title = tooltip_lines(row["label"], [("Type", ntype), ("Description", row.get("description", "")), ("Connections", str(degree.get(node_id, 0)))])
        net.add_node(
            node_id,
            label=row["label"],
            title=title,
            color=TYPE_COLORS.get(ntype, "#cccccc"),
            shape=TYPE_SHAPES.get(ntype, "dot"),
            size=size,
        )

    for _, row in edges_df.iterrows():
        label = row["relation"] if show_edge_labels else ""
        title = tooltip_lines(f"{row['source']} ↔ {row['target']}", [("Relation", row["relation"]), ("Description", row.get("description", ""))])
        net.add_edge(row["source"], row["target"], label=label, title=title, width=2)

    net.set_options(
        """
        {
          "interaction": {
            "hover": true,
            "tooltipDelay": 120,
            "hideEdgesOnDrag": false,
            "navigationButtons": true,
            "keyboard": true
          },
          "nodes": {
            "borderWidth": 1,
            "font": {"size": 18, "face": "arial", "strokeWidth": 3, "strokeColor": "#ffffff"}
          },
          "edges": {
            "smooth": {"type": "dynamic"},
            "font": {"size": 13, "align": "middle", "strokeWidth": 4, "strokeColor": "#ffffff"},
            "color": {"color": "#777777", "highlight": "#cc8800", "hover": "#cc8800"}
          },
          "physics": {
            "enabled": true,
            "stabilization": {"iterations": 250, "fit": true}
          }
        }
        """
    )
    return net


def render_net(net: Network):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        net.save_graph(f.name)
        html_doc = Path(f.name).read_text(encoding="utf-8")
    # Make default vis tooltip preserve line breaks and wrap on mobile.
    html_doc = html_doc.replace(
        "</head>",
        """
        <style>
          div.vis-tooltip {
            white-space: pre-wrap !important;
            max-width: min(420px, 86vw) !important;
            overflow-wrap: anywhere !important;
            line-height: 1.35 !important;
            font-family: Arial, sans-serif !important;
            font-size: 14px !important;
            padding: 10px 12px !important;
            border-radius: 8px !important;
          }
        </style>
        </head>
        """
    )
    components.html(html_doc, height=790, scrolling=True)


def detail_card(title: str, rows: list[tuple[str, str]]):
    st.markdown(f"### {clean_text(title)}")
    for key, value in rows:
        if clean_text(value):
            st.markdown(f"**{clean_text(key)}**")
            st.write(clean_text(value))


nodes, edges = load_tables()

st.title("Avantasia Collaboration Network")
st.caption("Interactive physics map of Avantasia guests, bands, side projects and cross-links. Files are flat: app.py, nodes.csv, edges.csv.")
st.write(f"Showing **{len(nodes)} nodes** and **{len(edges)} relationships**.")

with st.sidebar:
    st.header("Graph controls")
    selected_types = st.multiselect("Node types", sorted(nodes["type"].unique()), default=sorted(nodes["type"].unique()))
    show_edge_labels = st.checkbox("Show relationship labels on graph", value=False, help="Turn off on mobile; labels can become visually crowded.")
    physics_strength = st.slider("Physics repulsion", min_value=1200, max_value=9000, value=4200, step=400)
    st.caption("Hover/tap nodes or edges for a plain-text tooltip. Use the panels below for readable details.")

nodes_f = nodes[nodes["type"].isin(selected_types)].copy()
valid_ids = set(nodes_f["id"])
edges_f = edges[edges["source"].isin(valid_ids) & edges["target"].isin(valid_ids)].copy()

net = build_network(nodes_f, edges_f, show_edge_labels, physics_strength)
render_net(net)

st.divider()
col1, col2 = st.columns(2)

with col1:
    st.subheader("Node details")
    label_to_id = dict(zip(nodes_f["label"], nodes_f["id"]))
    label_choices = sorted(label_to_id)
    default_idx = label_choices.index("Avantasia") if "Avantasia" in label_choices else 0
    chosen_label = st.selectbox("Select artist, band or project", label_choices, index=default_idx)
    nrow = nodes_f[nodes_f["id"] == label_to_id[chosen_label]].iloc[0]
    connected = edges_f[(edges_f["source"] == nrow["id"]) | (edges_f["target"] == nrow["id"])]
    detail_card(nrow["label"], [("Type", nrow["type"]), ("Description", nrow["description"]), ("Number of visible links", str(len(connected)))])
    if not connected.empty:
        st.markdown("**Visible links**")
        for _, e in connected.sort_values("relation").head(60).iterrows():
            other = e["target"] if e["source"] == nrow["id"] else e["source"]
            other_label = nodes.set_index("id").loc[other, "label"] if other in set(nodes["id"]) else other
            st.write(f"• {other_label} — {e['relation']}")

with col2:
    st.subheader("Relationship details")
    edge_labels = []
    edge_map = {}
    node_label = nodes.set_index("id")["label"].to_dict()
    for i, e in edges_f.reset_index(drop=True).iterrows():
        txt = f"{node_label.get(e['source'], e['source'])} ↔ {node_label.get(e['target'], e['target'])} — {e['relation']}"
        edge_labels.append(txt)
        edge_map[txt] = i
    if edge_labels:
        chosen_edge = st.selectbox("Select relationship", edge_labels)
        erow = edges_f.reset_index(drop=True).iloc[edge_map[chosen_edge]]
        detail_card(
            f"{node_label.get(erow['source'], erow['source'])} ↔ {node_label.get(erow['target'], erow['target'])}",
            [("Relation", erow["relation"]), ("Description", erow["description"])],
        )
    else:
        st.info("No relationships visible with the current filters.")

st.divider()
st.subheader("Edit the dataset")
st.write("To extend the map, edit `nodes.csv` and `edges.csv`. Keep IDs stable and use plain text in description fields. Do not paste HTML into CSV cells.")
