# Local Vericant preview

The repository includes a local-only Flask runner for visual and functional testing before a PythonAnywhere deployment.

From the project root:

```powershell
python -m pip install -r requirements.txt
python scripts/run_local_preview.py
```

Open <http://127.0.0.1:5050/>.

To preview the temporary production announcement banner:

```powershell
python scripts/run_local_preview.py --show-rollout-banner
```

The runner forces `PA_MYSQL_BUILD_URL=0`, disables the SSH tunnel, and uses the ignored local database `instance/local-preview.db`. It does not load customer data or connect to the PythonAnywhere MySQL database.

Use `Ctrl+C` in the running terminal to stop the preview.
