# Avantasia Collaboration Network

A flat-file Streamlit app for an interactive Avantasia collaboration network.

## Files

Keep all files in the same repository folder:

```text
app.py
nodes.csv
edges.csv
requirements.txt
README.md
```

No `data/` folder is required.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Cloud

1. Push all root files to GitHub.
2. Create a Streamlit Cloud app.
3. Set main file to `app.py`.

## Editing the graph

Add people, bands and projects to `nodes.csv`.
Add links to `edges.csv`.

Important: keep descriptions as plain text. Do not paste HTML tags such as `<div>` or `<br>` into the CSV.
