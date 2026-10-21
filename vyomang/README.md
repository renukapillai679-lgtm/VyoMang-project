# VyoMang

Front end (port 5500) + FastAPI back end (port 8000) + SQLite database, with email login and Google Sign-In.

```
vyomang/
  backend/
    main.py          routes, CORS, /auth/google
    database.py      SQLite connection (vyomang.db is created automatically)
    models.py        tables: User, Sku, Sale, SaleOriginal, PurchaseOrder
    auth.py          passwords, JWT tokens, Google token verification
    forecast.py      demand forecast and reorder recommendations
    seed.py          sample data (only added when the database is empty)
    requirements.txt
  frontend/
    index.html       the whole web app (its script is inside this file)
```

## Run it (two terminals, both opened in the vyomang folder)

**Terminal 1: backend (port 8000)**

Windows
```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```
Mac / Linux
```
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn main:app --reload --port 8000
```

**Terminal 2: frontend (port 5500)**
```
python -m http.server 5500 --directory frontend
```
(Mac: `python3 -m http.server 5500 --directory frontend`)

Open **http://localhost:5500** (use `localhost`, not `127.0.0.1`, see below).
Demo login: demo@vyomang.com / demo1234. API explorer: http://localhost:8000/docs

## Google Sign-In checklist (Google Cloud Console > APIs & Services > Credentials > your OAuth client)
1. **Authorized JavaScript origins** must include `http://localhost:5500` and `http://localhost`.
   (Add `http://127.0.0.1:5500` too if you want to open the app at that address.)
2. If the OAuth consent screen is in **Testing** mode, add your Google account under **Test users**.
3. No client secret is needed for this login flow. The server only checks the ID token against your Client ID.
   **Never put `client_secret*.json` in the project or share it.** If it was shared, create a new secret in the console and delete the old one.
4. Origins changed in the console can take a few minutes to apply.

## How login works
1. You click the Google button and a popup opens (`data-ux_mode="popup"`).
2. Google gives the page an ID token. `handleCredentialResponse` in index.html POSTs it to `http://localhost:8000/auth/google`.
3. The server verifies the token with Google's public keys (`google-auth`), then finds or creates the user in the `users` table.
4. The server returns a signed app token (JWT, valid 12 hours). The page sends it as `Authorization: Bearer ...` on every request.
Email + password accounts use the same JWT.

## Troubleshooting
- **Google popup says "origin_mismatch" or the button is blank:** the address in your browser bar is not listed under Authorized JavaScript origins.
- **"Cannot reach the VyoMang server":** the backend is not running in terminal 1, or it is not on port 8000.
- **Browser console shows a CORS error:** open the app at http://localhost:5500 or http://127.0.0.1:5500 (those are the allowed origins).
- **"Could not reach Google to verify your sign-in":** the server has no internet access.
- **ModuleNotFoundError (jwt, sqlalchemy, google):** the venv is not active, or run `pip install -r requirements.txt` again.
- **Start from fresh data:** stop the server and delete `backend/vyomang.db`.
- **Existing vyomang.db from the older version:** it is upgraded automatically on the next start and keeps your users, products, sales and orders.

## Before a real launch
Set `JWT_SECRET` as an environment variable, serve over HTTPS, add your real domain to the allowed CORS origins and Google origins, and move to PostgreSQL.
