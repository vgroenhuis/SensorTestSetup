The lab demos page for this setup (https://closer.ram.eemcs.utwente.nl/labdemos/demo?id=sensortest). On the server,
copy `demo.json` and `README.md` into `labdemos/demos/sensortest/` (next to `sensortest.jpg`, which is only there). The
page reads the folder on every request: no restart needed.

`server-patches/own-page-and-relay-buttons.patch` (for `labdemos/static/labdemos.js`, all demos): "Device's own page"
goes to the device's own address (plain HTTP, university network), and a second button "Through this site (relay)" to
the relayed page (HTTPS, any network), for demos with `"proxy": true`. Apply in the server's checkout with
`git apply <patch>` (made against the backup of 2026-11-18, a8ddb5c); the page needs no restart.
