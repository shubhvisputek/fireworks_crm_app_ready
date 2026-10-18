# Shared Online Deployment

The Render Blueprint in `render.yaml` runs one CRM web service with a persistent disk for the SQLite database and the session-signing key. Invoice PDFs, exports and backups are generated on demand and not stored. Both computers use the same hosted URL and database. Keep the service at one instance; Render disks are attached to a single instance and SQLite is not a multi-instance database.

## Deploy

1. Push this project to a private GitHub repository. Do not commit `data/fireworks.db`, `data/.secret`, customer records, bills, or exports.
2. In Render, create a Blueprint from that repository and select `render.yaml`.
3. When prompted for `FIREWORKS_ADMIN_PASSWORD`, set a unique password with at least 12 characters. The login username is `admin`.
4. Wait for the service to deploy, then use the generated `https://...onrender.com` address on both computers.
5. Import the product catalog through Products → Upload Product Master. The new hosted database starts empty; local products and invoice history are not copied automatically.
6. Using your own domain (for example `billing.myshop.in`)? Add it to `FIREWORKS_ALLOWED_HOSTS` in the Render environment. The app refuses requests for host names it doesn't know, which protects it from DNS-rebinding attacks. The `onrender.com` address is allowed automatically.

The persistent disk is required and may incur hosting charges. The hosted service is public on the internet, so protect the login password and download regular backups from Backup & Export. Never share the backup URL or backup files publicly.

To migrate historical invoices as well as products, perform a separate, verified database migration before using the hosted system for new sales. The app's JSON backup currently has no restore workflow.