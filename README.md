# AlgoLevel Studio

Web app for creating short AlgoLevel marketing videos from real chart recordings. Upload four clips, preview the script, render a 24-second vertical MP4, and download its caption, plan, and thumbnail.

## Run locally

Install FFmpeg and DejaVu fonts, then:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000. Or use Docker:

```bash
docker build -t algolevel-studio .
docker run --rm -p 8000:8000 -v "$(pwd)/data:/app/data" algolevel-studio
```

An optional AI-written script requires `OPENAI_API_KEY` in the server environment. By default, the local template is free and needs no key. Voiceover is delivered as a script; the web renderer currently creates captioned silent video. The CLI supports `--voice` and optional API voice generation if you want audio in a local render.

## Deploy

Deploy the Dockerfile to a container host with persistent disk mounted at `/app/data`, at least 1 GB RAM, FFmpeg CPU time, and a 400 MB upload allowance. Set `PORT=8000` if the host requires it. The app has **no login**: keep the initial deployment private or add authentication and cleanup limits before sharing a public link. Render jobs are kept in process memory; a restart loses job status and stored files remain on disk.

Only upload footage you may use. Check the resulting claims and chart details before posting. The render crops footage to 9:16 around its center.

The included `agent.py` also works as a CLI; see `python agent.py --help`.
