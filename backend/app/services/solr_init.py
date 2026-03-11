"""
Ensure Solr **cores** exist (create if missing). Called at app startup.

We are running Solr in standalone mode (not SolrCloud), so we use the
Core Admin API instead of the Collections API.
"""
import httpx
from app.config import settings


def _core_admin_url() -> str:
  base = settings.solr_url.rstrip("/")
  # settings.solr_url is like http://localhost:8983/solr
  return f"{base}/admin/cores"


def ensure_cores() -> None:
  cores = [
      settings.solr_semantic_collection,
      settings.solr_layout_collection,
      settings.solr_metadata_collection,
  ]
  try:
      status_resp = httpx.get(
          _core_admin_url(),
          params={"action": "STATUS", "wt": "json"},
          timeout=10,
      )
      status_data = status_resp.json()
      existing = set((status_data.get("status") or {}).keys())
  except Exception:
      existing = set()

  for name in cores:
      if name in existing:
          continue
      try:
          # Create core using the _default configSet
          httpx.get(
              _core_admin_url(),
              params={
                  "action": "CREATE",
                  "name": name,
                  "instanceDir": name,
                  "configSet": "_default",
                  "wt": "json",
              },
              timeout=30,
          )
      except Exception:
          # For demo purposes, ignore failures (e.g. already exists)
          continue
