# Hosting MARG for your portfolio

There are two ways. **Use the demo version** for a portfolio: it needs no backend, costs nothing, never goes down, and strangers cannot write to your database or spend your Claude credits.

## A. Demo version (recommended): frontend only on Vercel

The demo serves saved snapshots of the real API (`frontend/public/demo/`, 9.9 MB, captured from your Supabase data and real Claude answers). A visitor can use every screen, the ward map, the budget slider, road receipts and notices. Reports, replies and sign-in work too, but are kept only in that visitor's browser.

1. Push the `demo-site` branch to GitHub.
2. Vercel → Add New → Project → import the repo, branch `demo-site`.
3. Settings:
   - **Root Directory:** `frontend`
   - **Framework preset:** Vite
   - **Build command:** `npm run build:demo`
   - **Output directory:** `dist`
   - No environment variables are needed.
4. Deploy. Link to the Vercel address from your portfolio, or embed it in an `<iframe>`.

What visitors can try:
- **Ask:** tap one of the sample questions to see a saved answer written by Claude.
- **Report:** send a report from a road receipt, then see it under My reports.
- **Ward office:** sign in as `officer@demo.in` with any password, open the report by its number, mark it, and watch the citizen's tracker update.
- **Defect notice:** Kurla Andheri Road and seven other roads have saved Claude-written notices in English and Marathi. Other roads show a friendly note.

To refresh the snapshots after the data changes, start the backend and run `python frontend/scripts/capture_demo.py`, then redeploy. For local use: `npm run dev:demo`.

## B. Live backend (only if you need it fully live)

The backend is FastAPI plus Supabase. `render.yaml` (repo root) is a Render blueprint; it has not been deployed or tested.

1. Render → New → **Blueprint** → pick the repo. When asked, paste `DATABASE_URL`, `ANTHROPIC_API_KEY` and the two `SUPABASE_S3_*` keys into Render's dashboard. Never put secrets in the repo or in chat.
2. Check `https://<service>.onrender.com/api/health`.
3. The backend loads xgboost, shap and pandas and may run out of memory on Render's free 512 MB plan. If it restarts in a loop, use the starter plan (about $7/month), Railway or Fly.
4. Create the first officer with `python -m backend.admin_cli create-admin ...` (with the same `DATABASE_URL`).
5. On Vercel use the normal build (`npm run build`) and set `VITE_API_BASE` to the https address.

Before making a live site public:
- Set a monthly spend limit on the Anthropic key.
- Ask the backend owner to restrict CORS in `backend/main.py` (now `*`) to your Vercel domain and to rate-limit the report, reply and citizen-query endpoints.
- Delete the "FRONTEND TEST" reports (ids 6 and up).
