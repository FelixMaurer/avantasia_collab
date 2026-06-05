import html
import math
from pathlib import Path

import networkx as nx
import pandas as pd
import streamlit as st
from pyvis.network import Network
import streamlit.components.v1 as components

APP_DIR = Path(__file__).parent
DATA_PATH = APP_DIR / "data" / "collaborators.csv"

st.set_page_config(page_title="Avantasia Collaboration Network", layout="wide")
st.title("Avantasia collaboration network")
st.caption("Interactive spring/physics map of Avantasia guest singers/musicians and their linked bands.")

@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path).fillna("")
    df["band_list"] = df["bands"].apply(lambda s: [b.strip() for b in str(s).split(";") if b.strip()])
    return df

def build_graph(df: pd.DataFrame, include_band_band: bool, include_shared_band_people: bool, min_band_degree: int) -> nx.Graph:
    G = nx.Graph()
    G.add_node("Avantasia", type="center", label="Avantasia", title="Avantasia: central project", size=45)

    band_counts = {}
    for bands in df["band_list"]:
        for b in bands:
            band_counts[b] = band_counts.get(b, 0) + 1

    for _, row in df.iterrows():
        singer = row["singer"]
        if not singer:
            continue
        bands = [b for b in row["band_list"] if band_counts.get(b, 0) >= min_band_degree]
        tooltip = f"<b>{html.escape(singer)}</b><br>Role: {html.escape(row['role'])}<br>Notes: {html.escape(row['notes'])}<br>Bands: {html.escape('; '.join(bands))}"
        G.add_node(singer, type="person", label=singer, title=tooltip, size=18 + min(12, len(bands) * 2))
        G.add_edge("Avantasia", singer, type="avantasia_collab", title="Avantasia collaborator", weight=4)
        for band in bands:
            G.add_node(band, type="band", label=band, title=f"<b>{html.escape(band)}</b>", size=12 + min(10, band_counts.get(band, 1) * 3))
            G.add_edge(singer, band, type="member_affiliation", title=f"{singer} ↔ {band}", weight=2)

    if include_band_band:
        person_to_bands = {row["singer"]: [b for b in row["band_list"] if band_counts.get(b, 0) >= min_band_degree] for _, row in df.iterrows()}
        for singer, bands in person_to_bands.items():
            for i in range(len(bands)):
                for j in range(i + 1, len(bands)):
                    if G.has_node(bands[i]) and G.has_node(bands[j]):
                        G.add_edge(bands[i], bands[j], type="shared_person", title=f"Shared link: {singer}", weight=1)

    if include_shared_band_people:
        band_to_people = {}
        for _, row in df.iterrows():
            for b in row["band_list"]:
                if band_counts.get(b, 0) >= min_band_degree:
                    band_to_people.setdefault(b, []).append(row["singer"])
        for band, people in band_to_people.items():
            for i in range(len(people)):
                for j in range(i + 1, len(people)):
                    if G.has_node(people[i]) and G.has_node(people[j]):
                        G.add_edge(people[i], people[j], type="same_band", title=f"Both linked to {band}", weight=1)
    return G

def pyvis_html(G: nx.Graph, height: int, physics: bool, search: bool) -> str:
    net = Network(height=f"{height}px", width="100%", bgcolor="#111111", font_color="#eeeeee", notebook=False, cdn_resources="in_line")
    net.from_nx(G)

    colors = {"center": "#ffcc00", "person": "#65b5ff", "band": "#ff7676"}
    shapes = {"center": "star", "person": "dot", "band": "triangle"}
    edge_colors = {"avantasia_collab": "#ffcc00", "member_affiliation": "#cccccc", "shared_person": "#666666", "same_band": "#55ffaa"}

    for node in net.nodes:
        typ = node.get("type", "band")
        node["color"] = colors.get(typ, "#cccccc")
        node["shape"] = shapes.get(typ, "dot")
        node["font"] = {"size": 18 if typ == "center" else 13, "color": "#eeeeee"}
        node["borderWidth"] = 2

    for edge in net.edges:
        typ = edge.get("type", "member_affiliation")
        edge["color"] = edge_colors.get(typ, "#999999")
        edge["smooth"] = {"type": "continuous"}
        if typ in {"shared_person", "same_band"}:
            edge["dashes"] = True
            edge["width"] = 0.8
        elif typ == "avantasia_collab":
            edge["width"] = 2.5
        else:
            edge["width"] = 1.3

    net.set_options(f"""
    var options = {{
      "nodes": {{"scaling": {{"min": 8, "max": 45}}}},
      "edges": {{"scaling": {{"min": 1, "max": 4}}, "selectionWidth": 3}},
      "interaction": {{"hover": true, "tooltipDelay": 120, "navigationButtons": true, "keyboard": true, "multiselect": true}},
      "physics": {{
        "enabled": {str(physics).lower()},
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {{"gravitationalConstant": -90, "centralGravity": 0.012, "springLength": 135, "springConstant": 0.08, "damping": 0.55, "avoidOverlap": 0.8}},
        "stabilization": {{"enabled": true, "iterations": 900, "updateInterval": 50}}
      }}
    }}
    """)
    html_text = net.generate_html()
    if search:
        # simple browser find works, but this hint is useful inside Streamlit iframe
        html_text = html_text.replace("</body>", "<div style='position:fixed;bottom:8px;left:8px;color:#bbb;font:12px sans-serif;background:#222;padding:6px;border-radius:6px'>Tip: click/drag nodes, scroll to zoom, use browser find for names.</div></body>")
    return html_text


df = load_data(DATA_PATH)

with st.sidebar:
    st.header("Graph options")
    query = st.text_input("Filter people/bands", "")
    include_band_band = st.checkbox("Add band ↔ band edges via shared person", True)
    include_shared_band_people = st.checkbox("Add singer ↔ singer edges via shared band", False)
    min_band_degree = st.slider("Hide bands linked to fewer than N listed people", 1, 4, 1)
    physics = st.checkbox("Enable spring physics", True)
    height = st.slider("Graph height", 500, 1200, 800, 50)

filtered = df.copy()
if query.strip():
    q = query.strip().lower()
    filtered = filtered[
        filtered["singer"].str.lower().str.contains(q, regex=False)
        | filtered["bands"].str.lower().str.contains(q, regex=False)
        | filtered["notes"].str.lower().str.contains(q, regex=False)
    ]

G = build_graph(filtered, include_band_band, include_shared_band_people, min_band_degree)

c1, c2, c3 = st.columns(3)
c1.metric("Nodes", G.number_of_nodes())
c2.metric("Edges", G.number_of_edges())
c3.metric("Collaborators shown", len(filtered))

components.html(pyvis_html(G, height=height, physics=physics, search=True), height=height + 20, scrolling=False)

with st.expander("Data table"):
    st.dataframe(filtered.drop(columns=["band_list"]), use_container_width=True)
    st.download_button("Download filtered CSV", filtered.drop(columns=["band_list"]).to_csv(index=False), "avantasia_network_filtered.csv", "text/csv")

with st.expander("How to extend the network"):
    st.markdown(
        "Edit `data/collaborators.csv`. Add one row per Avantasia collaborator; separate bands with semicolons. "
        "The app automatically creates Avantasia→person and person→band edges, plus optional inferred crosslinks."
    )
