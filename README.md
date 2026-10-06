<!-- mcp-name: io.github.sepehr071/doctoreto-mcp -->

<div align="center">

<img src="https://raw.githubusercontent.com/sepehr071/doctoreto-mcp/main/.github/banner.png" alt="doctoreto-mcp: let your AI agent compare visit fees and free times on Doctoreto" width="100%">

# 🩺 doctoreto-mcp

**Let your AI agent find the right doctor on Doctoreto.**<br>
Search Iranian doctors by speciality, city, neighborhood and visit type, compare visit fees,<br>
see free appointment times, read reviews, and find hospitals, labs and clinic offers, all from Claude, Cursor or Copilot.

[![PyPI](https://img.shields.io/pypi/v/doctoreto-mcp?color=2563eb)](https://pypi.org/project/doctoreto-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/doctoreto-mcp)](https://pypi.org/project/doctoreto-mcp/)
[![CI](https://github.com/sepehr071/doctoreto-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sepehr071/doctoreto-mcp/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.sepehr071%2Fdoctoreto--mcp-7c3aed)](https://registry.modelcontextprotocol.io/?q=doctoreto-mcp)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/doctoreto-mcp/blob/main/LICENSE)

[![Install in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=doctoreto&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJkb2N0b3JldG8tbWNwIl19)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_doctoreto--mcp-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=doctoreto&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22doctoreto-mcp%22%5D%7D)

[Quick start](#quick-start) · [What it can do](#what-it-can-do) · [Tools](#tools) · [FAQ](#faq) · [فارسی](#فارسی)

</div>

---

## Why

On Doctoreto (doctoreto.com) a doctor card shows a name and a rating, but the things you decide on are a few
clicks deeper: which offices the doctor has, what the visit costs at the office (often hidden on the page), what a
phone or video consultation costs, and when the next free time actually is. An agent with `doctoreto-mcp` reads the
search, the doctor's services and the slot picker, and hands you the booking link:

> **You:** A cardiologist in Pasdaran, Tehran, as soon as possible. What does the visit cost?
>
> **Agent:** *calls* `dt_search_doctors(city="tehran", speciality="cardiologist", neighborhood="pasdaran", has_free_slot=True)` → `dt_doctor(doctor="xqbEWZ")` → `dt_free_slots(consultation_id=1943, days=7)`
>
> | Service | Fee | Paid when booking | Next free |
> |---|---:|---:|---|
> | Office visit, Pasdaran | 250,000 | 0 | Tue 6 Oct, 10:00 (25 free times that day) |
> | Phone call, 15 minutes | 750,000 | 750,000 | Tue 6 Oct, 10:00 |
>
> دکتر کامبیز پرآذران, subspecialist in cardiology: 408 reviews, 92% recommend, about 36 minutes wait at the
> office. The office fee is paid at the office. Book here: https://doctoreto.com/doctor/dr-kambiz-parazaran/xqbEWZ

<sub>Real tool output from 2026-10-06; prices and free times change all the time. Prices are in Toman.</sub>

## What it can do

- 🔎 **Find doctors** by speciality, city, neighborhood, name, gender, insurance and visit type (office, phone, text, video, instant)
- ⏱️ **Soonest first**: sort by the earliest free slot, by popularity or by number of bookings; search near a point
- 💰 **Real prices**: office visit fee (also when the site hides it), online consultation prices, deposits
- 📅 **Free times**: free appointment times per day for any office or online service, up to a month ahead
- ⭐ **Reviews**: stars, recommend rate, waiting time, per-category averages; reviewer names are never returned
- 🏥 **Centers**: hospitals, clinics, laboratories, imaging, pharmacies (24h, state/private, map search), hours and insurances
- 🏷️ **Clinic offers**: fixed-price procedures (ultrasound, echo, laser, check-ups) with deposits and free times
- 📖 **Health magazine**: background articles on conditions and tests
- 🔒 **Read-only by design**: no login, no booking, no payment; the agent gives you the link to book

## Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/).

<details open>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add doctoreto -- uvx doctoreto-mcp
```
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Settings → Developer → Edit Config, then add:

```json
{
  "mcpServers": {
    "doctoreto": { "command": "uvx", "args": ["doctoreto-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Cursor</b></summary>

Click **Install in Cursor** above, or add the Claude Desktop block to `~/.cursor/mcp.json`.
</details>

<details>
<summary><b>VS Code (Copilot agent mode)</b></summary>

Click **Install in VS Code** above, or add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "doctoreto": { "type": "stdio", "command": "uvx", "args": ["doctoreto-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Anything else</b></summary>

It's a standard stdio MCP server: run `uvx doctoreto-mcp`, or `pip install doctoreto-mcp` and run `doctoreto-mcp`.
</details>

Then just ask:

- "A female dermatologist in Shiraz with a free slot this week, and her visit fee?"
- "Which pediatricians offer a video call today, and how much is it?"
- "A 24-hour pharmacy near Vanak Square."
- "How much is an echocardiography at a Doctoreto clinic in Tehran, and when is the next free time?"
- <span dir="rtl">یک متخصص گوش و حلق و بینی در محدوده سعادت&zwnj;آباد با بیمه تامین اجتماعی</span>

## How it works

```text
  AI agent  (Claude, Cursor, Copilot, ...)
      │
      │  MCP over stdio
      ▼
  doctoreto-mcp  (runs on your machine)
      │
      │  HTTPS (JSON)
      ├──────▶  api.doctoreto.com   (doctors, slots, reviews, centers, offers)
      └──────▶  doctoreto.com/blog   (health magazine)
```

`doctoreto-mcp` runs locally and calls the same public endpoints the Doctoreto website uses.
There's no hosted server in between, no API key, and nothing about you is sent anywhere else.

## Tools

Doctors, centers and offers are identified by a 6-character id (`xqbEWZ`, the last part of
`doctoreto.com/doctor/dr-kambiz-parazaran/xqbEWZ`); every tool also accepts the page URL itself.

<details open>
<summary><b>🔎 Find a doctor</b> (6)</summary>

| Tool | What it does |
|---|---|
| `dt_suggest` | Free phrase → matching doctors, speciality slugs, service tags and centers |
| `dt_search_doctors` | Doctors by city, speciality, neighborhood, name, gender, insurance, visit type, free slot; sorting |
| `dt_specialities` | Speciality list with the slugs the search needs |
| `dt_cities` | City slug and id; cities that have a speciality, with doctor counts |
| `dt_neighborhoods` | Neighborhoods of a city and nearby cities, with doctor counts |
| `dt_insurances` | Basic and supplementary insurers with their ids |
</details>

<details open>
<summary><b>🩺 One doctor</b> (3)</summary>

| Tool | What it does |
|---|---|
| `dt_doctor` | Profile, every office and online service with fee, deposit, address and next free time, review summary |
| `dt_free_slots` | Free appointment times per day for one service (office, phone, video, offer, lab), up to 31 days |
| `dt_reviews` | Reviews of a doctor, center or offer: stars, text, labels, waiting time, replies (no names) |
</details>

<details open>
<summary><b>🏥 Centers</b> (2)</summary>

| Tool | What it does |
|---|---|
| `dt_search_centers` | Hospitals, clinics, labs, imaging, pharmacies by city, type, 24h, state/private, or near a point |
| `dt_center` | One center: hours, departments, insurances, lab rules, bookable services, doctors |
</details>

<details open>
<summary><b>🏷️ Clinic offers and reading</b> (3)</summary>

| Tool | What it does |
|---|---|
| `dt_search_offers` | Fixed-price procedures and packages by text, city, speciality, price range, doctor or place |
| `dt_offer` | One offer: price, deposit, provider, terms, variants with their free times |
| `dt_health_articles` | Doctoreto health magazine articles on a condition, test or treatment |
</details>

All 14 tools are annotated `readOnlyHint: true` and return compact structured JSON, so they don't flood the agent's context.

## Good to know

- **Prices are in Toman.** For an office visit `fee` is what you pay at the office and `pay_online_now` what is charged when booking (usually 0). For phone, text and video `fee` is the online price. A `null` fee means the doctor lists none.
- **Use `dt_doctor` for online prices.** The search list and the profile show a phone price three times the one on the booking page; `dt_doctor` reads the booking box, which matches the page.
- **Dates are Gregorian** `YYYY-MM-DD` (1405-07-22 = 2026-10-14); times are Tehran local. Jalali dates are given next to them.
- **Booking happens on the site.** It needs an SMS code, so the agent finds the doctor and time and gives you the page link.
- **Insurance:** few doctors list insurances, so `insurance_ids` narrows a search a lot. Centers list theirs in `dt_center`; the center search ignores insurance filters.
- **Reviews:** doctor and center reviews come newest first, offer reviews oldest first; each review date is the Tehran day, as on the page.
- **Search pages** hold exactly `limit` doctors, also when the site mixes sponsored doctors in.
- **Privacy:** no phone numbers and no reviewer names are returned.
- **Checked against the website:** on 2026-10-06 every tool's output was compared with the live doctoreto.com pages (names, fees, free times per day, review order, search totals and order, centers, offers).

## FAQ

<details>
<summary><b>Can it book an appointment for me?</b></summary>

No, and that's deliberate. It has no login and never calls the booking, payment, review or chat endpoints.
The agent finds the doctor, the service and a free time; you book on doctoreto.com with your own phone number.
</details>

<details>
<summary><b>"slug alone cannot be resolved"</b></summary>

Doctoreto's API needs the 6-character id, not the name slug. Paste the whole page URL
(`https://doctoreto.com/doctor/<slug>/<id>`), or let the agent search by the doctor's Persian name.
</details>

<details>
<summary><b>Do I need an Iranian IP?</b></summary>

No geo block was seen: direct calls and calls through a proxy in Turkey both worked (2026-10-06). Cloud servers
were not tested; if Doctoreto blocks one, set `DOCTORETO_MCP_PROXY`.
</details>

<details>
<summary><b>A search returns 0 doctors</b></summary>

The filters may be too narrow (an insurance plus a neighborhood often is). Drop a filter, or check the slugs with
`dt_suggest`, `dt_specialities` or `dt_neighborhoods`. An unknown city or speciality slug returns an error.
</details>

<details>
<summary><b>Claude Desktop says <code>uvx</code> is not found</b></summary>

Use the full path to `uvx` (`where uvx` on Windows, `which uvx` on macOS/Linux) as `command`.
</details>

<details>
<summary><b>How do I debug what the agent sees?</b></summary>

```bash
npx @modelcontextprotocol/inspector uvx doctoreto-mcp
```
</details>

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DOCTORETO_MCP_PROXY` | unset | HTTP proxy for every request, e.g. `http://user:pass@host:port` |

## فارسی

<div dir="rtl">

**doctoreto-mcp** به دستیار هوش مصنوعی شما (Claude، Cursor، Copilot و ...) اجازه می&zwnj;دهد در دکترتو پزشک مناسب را
بر اساس تخصص، شهر، محله، بیمه و نوع ویزیت (حضوری، تلفنی، متنی، تصویری) پیدا کند، هزینه ویزیت و زمان&zwnj;های خالی نوبت
را ببیند، نظرات بیماران را بخواند و بیمارستان، آزمایشگاه و خدمات دکترتو کلینیک را هم جست&zwnj;وجو کند.

- فقط خواندنی است: وارد حساب نمی&zwnj;شود، نوبت رزرو نمی&zwnj;کند و پرداخت نمی&zwnj;کند؛ لینک صفحه پزشک را برای رزرو می&zwnj;دهد.
- همه قیمت&zwnj;ها به تومان است.
- شماره تلفن و نام نظردهندگان را برنمی&zwnj;گرداند.
- روی سیستم خود شما اجرا می&zwnj;شود و به هیچ سرور واسطی داده نمی&zwnj;فرستد.

**نصب در Claude Code:**

</div>

```bash
claude mcp add doctoreto -- uvx doctoreto-mcp
```

<div dir="rtl">

بعد بپرسید: «یک متخصص قلب در پاسداران تهران با نزدیک&zwnj;ترین نوبت خالی، با هزینه ویزیت»

</div>

## Development

```bash
git clone https://github.com/sepehr071/doctoreto-mcp && cd doctoreto-mcp
uv sync
uv run pytest            # offline, against recorded responses
uv run pytest -m live    # real APIs
uv run ruff check .
```

Tools live in `src/doctoreto_mcp/search.py`, `doctor.py`, `centers.py`, `offers.py` and `info.py`; each is a typed
async function with a docstring that tells the agent when to use it. Issues and PRs are welcome, especially new tools
and fixes for API changes.

Releases: bump the version in `pyproject.toml` and `server.json`, then push a `v*` tag. GitHub Actions tests,
publishes to PyPI and the [MCP Registry](https://registry.modelcontextprotocol.io), and creates the GitHub Release.

## Disclaimer

Unofficial and not affiliated with or endorsed by Doctoreto. It uses the public endpoints of the doctoreto.com
website, which can change without notice. It gives information, not medical advice. Please keep request rates
reasonable.

## License

[MIT](https://github.com/sepehr071/doctoreto-mcp/blob/main/LICENSE)
