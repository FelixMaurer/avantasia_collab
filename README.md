# Avantasia Collaboration Network

A flat, GitHub-ready Streamlit app for exploring the Avantasia collaboration universe.

No folders are required. Keep all files in the repository root:

```text
app.py
nodes.csv
edges.csv
requirements.txt
README.md
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Cloud

1. Upload these files to the root of a GitHub repository.
2. In Streamlit Cloud, choose `app.py` as the entry point.
3. Do not put `nodes.csv` or `edges.csv` into a `data/` folder unless you also change the paths in `app.py`.

## Editing the graph

- Add artists, bands and projects to `nodes.csv`.
- Add relationships to `edges.csv`.
- The app validates missing IDs and reports broken edges in the sidebar.

## Data model

`nodes.csv` columns:

```csv
id,label,type,description,aliases,source_note
```

`edges.csv` columns:

```csv
source,target,relation,description,weight
```
