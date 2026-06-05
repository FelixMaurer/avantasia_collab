# Avantasia Collaboration Network

Interactive Streamlit/PyVis spring network of Avantasia collaborators and their linked bands.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository.
2. Add `app.py`, `requirements.txt`, and the `data/` folder.
3. In Streamlit Cloud, choose the repo and set the main file to `app.py`.

## Data model

`data/collaborators.csv` has:

- `singer`: collaborator / musician name
- `bands`: semicolon-separated band affiliations
- `role`: guest vocalist, guitar, drums, core musician, etc.
- `notes`: short context

The graph creates:

- Avantasia → collaborator edges
- collaborator → band edges
- optional band ↔ band edges where one person links both
- optional collaborator ↔ collaborator edges where both share a band

This is a curated seed dataset. It is intentionally easy to expand/correct by editing the CSV.
