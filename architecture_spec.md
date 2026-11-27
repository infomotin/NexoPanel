# Architecture & Functional Specification: Server Control Panel (Inspired by aaPanel 8.0.8)

This document captures the complete UI, layout, module inventory, data tables, forms, modals, and operational workflows observed in the live aaPanel `8.0.8` demo (`Debian 12`, `x86_64`), adapted as the clean-room blueprint for our full-stack React (Vite) + Tailwind CSS + Node.js (Express) + SQLite application.

> **Demo Environment Note:** In the live demo instance, the `Memo` widget explicitly notes `"Reset every 3 hours. Files, Terminal hidden"`. Both **Files** and **Terminal** are fully specified below for complete operational coverage.

---

## 1. Global Layout & Navigation Shell

### 1.1 Left Vertical Sidebar (Dark Theme)
* **Header:**
  * Server IP badge (e.g., `1.2.3.4`)
  * Notification counter badge (`0`)
  * Global Command Palette trigger (`Search (Ctrl+K)`)
* **Primary Navigation Menu (19 items):**
  1. `Home` (`/home`)
  2. `Website` (`/site/php`)
  3. `WP Toolkit` (`/wp/toolkit`)
  4. `FTP` (`/ftp`)
  5. `Databases` (`/database/mysql`)
  6. `Docker` (`/docker/overview`)
  7. `Monitor` (`/control/system`)
  8. `Security` (`/security/overview`)
  9. `WAF` (`/waf/overview`)
  10. `Mail Server` (`/mail/market`)
  11. `Logs` (`/logs/panel`)
  12. `Node` (`/node/manage`)
  13. `Domains` (`/ssl_domain/domain`)
  14. `Account` (`/aapanelsub/account`)
  15. `AI` (`/ai/chat`)
  16. `Cron` (`/crontab/task`)
  17. `App Store` (`/softs/app`)
  18. `Settings` (`/setting/all`)
  19. `Log out`
  * *(Plus `Files` and `Terminal` in non-demo deployments)*
* **Bottom Controls:** Sidebar collapse toggle & theme switcher.

### 1.2 Persistent Top Bar
* **Left (Context-Sensitive):** Horizontal sub-navigation tabs for the active module.
* **Right (Global Controls):**
  * Bound account/server alias (`aaP****.com`)
  * OS badge (`Debian 12`)
  * Edition & License badge (`PRO`, `Expire on`, `Renewal`)
  * Theme/Layout switcher (`Classic`)
  * Panel version (`8.0.8`)
  * Quick system actions: `Update`, `Fix`, `Restart`

### 1.3 Footer
* Copyright & external links (`Documentation`, `Forum`, `Support`: Telegram, Discord, Email).

---

## 2. Authentication (`/login`)
* **UI Components:** Centered card with Panel logo, `Username` input, `Password` input, `Sign In` submit button, and inline error banner (`Unauthorized` / rate-limit feedback).
* **Workflow:** `POST /api/auth/login` validates credentials, issues a signed JWT (and/or `HttpOnly` session cookie), and redirects to `/home`.

---

## 3. Home Dashboard (`/home`)
1. **Status / Resource Gauges (4-card row with circular SVG/Recharts gauges):**
   * `Load Status`: Status label (`Normal`) + 1m / 5m / 15m averages (`0.21 / 0.28 / 0.27`).
   * `CPU`: Core count (`4 Cores`) + real-time utilization percentage.
   * `RAM`: Used / Total (`990 MB / 3.82 GB`) + percentage gauge.
   * `Disk`: Used / Total (`35.3 GB / 96.2 GB`) on mount `/`.
2. **Overview Summary Cards (Draggable Grid):**
   * `Site - ALL`: Running count, Stopped count, Total count.
   * `FTP`: Total FTP accounts.
   * `Database`: Total databases.
   * `Security`: Security Risk count + Last Scan timestamp.
   * `Memo`: Inline editable server notes widget.
3. **Software Quick-Access Grid:**
   * Pinned installed services (`PHP 8.2.17`, `Pure-Ftpd 1.0.49`, `phpMyAdmin 5.2`, `Redis 7.2.7`, `Mail Server 7.3.7`, `MySQL 5.7.43`, `Nginx 1.24.0`, `Apache 2.4.62`, `OpenLiteSpeed 1.8.4`) with quick start/restart/config triggers.
   * Recommended plugin cards with `Install` buttons.
4. **Traffic / Disk IO Chart Widget:**
   * Tabs: `Traffic` | `Disk IO`
   * Interface selector (`Net: All`)
   * Real-time area/line chart (Recharts) + metrics (`Upstream`, `Downstream`, `Total sent`, `Total received`).

---

## 4. Core Management Modules

### 4.1 Website Manager (`/site/php`)
* **Sub-tabs:** `PHP Project` | `Node.js Project` | `Proxy Project` | `Go Project` | `Python Project` | `All Projects`
* **Toolbar:** `Add site`, `Advanced Setup`, `Statistics`, Webserver status pill (`Nginx 1.24.0`), `Category` filter, Search (`Domain or Remarks`).
* **Table Columns:** Checkbox, `Site name` (clickable URL + doc root), `Status` (inline Running/Stopped toggle + remarks), `Backup / Restore` (`0 Backup`, `Click to backup`), `Quick action` (open root folder, PHP version badge), `Expiration` (`Perpetual`), `SSL` (`Not Set` / active cert), `Requests`, `WAF`, `Operate` (`Conf`, `Log`, `Delete`).
* **Bulk Actions & Pagination:** Select-all, `Please choose` (`Start`, `Stop`, `Delete`) + `Execute`, `10 / page`.
* **Add Site Modal:**
  * Tabs: `Create site` | `One-click Deploy` | `Create for Git` | `Batch create` | `Create from backup`
  * Fields: `Domain name` (multiline), `Apply for SSL` checkbox, `Description`, `Website Path` (`/www/wwwroot`), `FTP` toggle, `Database` toggle (`MySQL`), `PHP version` (`PHP-82`, `PHP-83`, `Static`), `Site category`, `Create html file` switch, `Cancel` / `Confirm`.
* **Site `Conf` Drawer/Modal:** Domain aliases, Document Root, PHP version switcher, URL Rewrite presets, SSL toggle/Force HTTPS, Nginx config editor, and Site `Log` viewer.

### 4.2 FTP Manager (`/ftp`)
* **Banner:** `FTP address: ftp://<server-ip>:21`
* **Toolbar:** `Add FTP`, `Change FTP Port`, `FTP log analysis`, `FTP search`.
* **Table Columns:** Checkbox, `Username`, `Password` (masked/copy/reset), `Status` (Active/Disabled toggle), `Document Root`, `Quota`, `Note`, `Operate` (`Edit`, `Delete`).
* **Bulk Actions:** Delete selected + pagination.

### 4.3 Database Manager (`/database/mysql`)
* **Sub-tabs:** `MySQL` | `SQLServer` | `MongoDB` | `Redis` | `PgSQL`
* **Banner:** `Auto Backup Database` toggle switch.
* **Toolbar:** `Add DB`, `Root password`, `phpMyAdmin`, `Remote DB`, `Advanced Setup`, `Sync all`, `Get DB from server`, filter (`All`), `Database search`.
* **Table Columns:** Checkbox, `Database name`, `Username`, `Password` (masked/rotate), `Quota`, `Backup` (backup/restore), `Location` (`localhost` / `%`), `Note`, `Operate` (`Permissions`, `Import/Export`, `Delete`).
* **Bulk Actions:** Delete selected + pagination (`20 / page`).

### 4.4 File Manager (`/files`) *(Hidden in Demo; Full Spec)*
* **Toolbar:** Path breadcrumb bar, `Upload`, `New File`, `New Folder`, `Remote Download`, `Terminal`, `Trash / Recycle Bin`, `Search`.
* **Directory Tree & File Table:** Checkbox, `Name` (folder/file icon), `Permissions` (`0755` / `0644` clickable chmod modal), `Owner` (`www`), `Size`, `Modified`, `Operate` (`Edit`, `Rename`, `Copy`, `Compress/Extract`, `Download`, `Delete`).
* **Modals:**
  * **Inline Code/Text Editor:** Syntax-highlighted/monospace editor with `Save` & `Close`.
  * **Chmod Permissions Modal:** Owner/Group/Public Read/Write/Execute checkboxes + octal input (`755`).

### 4.5 Docker Manager (`/docker/overview` & `/docker/setting`)
* **Sub-tabs:** `Overview` | `Container` | `One-Click Install` | `Cloud image` | `Local image` | `Docker Compose` | `Network` | `Volume` | `Repository` | `Settings`
* **Container View:** List containers (`ID`, `Name`, `Image`, `Status`, `Ports`, `Actions`: Start/Stop/Restart/Logs/Remove).
* **Settings View:** Docker daemon status (`Start`, `Restart`, `Repair`), `Accelerate URL`, `Docker Compose` path, `Private Registry`, toggles (`Log Rotation`, `IPv6 Network`, `iptables`, `live_restore`), `One-Click Install Dir` (`/www/dk_project`), and System Info card.

### 4.6 System Monitor (`/control/system`)
* **Controls:** `Monitoring Status` toggle, `Number of days to save` + `Modify`, `Monitor Log Size` + `Clean Logs`.
* **Time Range Filters:** `Yesterday` | `Today` | `Last 7 days` | `Custom`
* **6 Historical Charts (Recharts):** `Load Average`, `CPU`, `Memory`, `Disk I/O`, `Network I/O` (interface selector `all`), `Swap Usage`.

### 4.7 Security & Firewall (`/security/overview` & `/security/firewall`)
* **Sub-tabs:** `Overview` | `Firewall` | `SSH` | `Server security` | `Website Security` | `Brute force protection` | `Compiler Access` | `Anti Intrusion` | `System Hardening` | `Scan Detection`
* **Overview:** Real-time protection status list + `Security check` (`Scan`, `Check Time`, `Risks found`).
* **Firewall:** `Turn on Firewall` & `Block ICMP` toggles; Sub-tabs (`Port rule`, `IP rules`, `Port forward`, `Area rules`); `Add Port Rule` modal, `Import/Export rules`, direction filter (`All`, `Inbound`, `Outbound`), port search; Table (`Protocol`, `Port`, `Status`, `Strategy`, `Direction`, `Source IP`, `Remarks`, `Add Time`, `Operate`); Batch delete.

### 4.8 Cron Jobs (`/crontab/task`)
* **Sub-tabs:** `Cron Job` | `Task Scheduling` | `Script library`
* **Add Task Form:** `Task type` (`Shell Script`, `Backup Site`, `Backup Database`, `Access URL`, `Free Memory`), `Task name`, `Execute cycle` (`Daily`, `Hours`, `Minutes`, `Multiple executions` / custom cron builder), `Execute user` (`root`), `Script content`, `Add Task` button.
* **Task Table:** `Name`, `Status` (Active/Paused), `Execute cycle`, `Retention Count`, `Backup to`, `Last execute time`, `Operate` (`Run Now`, `Log`, `Edit`, `Delete`), plus Import/Export & fuzzy search.

### 4.9 App Store (`/softs/app`)
* **Sub-tabs:** `Official App` | `Third-party Plug-ins`
* **Controls:** `Search App`, `Update App List`, Category pills (`ALL`, `Installed`, `Deployment`, `Tools`, `Plug-ins`, `Professional`), view toggle.
* **Table Columns:** `Software name`, `Developer`, `Instructions`, `Price`, `Expire date`, `Location`, `Status` (`Installed` / `Not Installed`), `Display on Home` switch, `Operate` (`Install` / `Uninstall` / `Settings`).

### 4.10 Terminal (`/terminal`) *(Hidden in Demo; Full Spec)*
* **UI:** Interactive web terminal console with command history, clear, and session status indicator.

### 4.11 Settings (`/setting/all`)
* **Sub-tabs:** `Global` | `Page` | `Alarm` | `Backup Restore` | `Migrate` | `Service`
* **Global Settings Sections:**
  * `Network & Access`: Domain, Panel port (`7800`), Security Entrance, Panel SSL toggle & certificate info.
  * `Advanced Features`: Developer mode, API toggle, API key & IP whitelist.
  * `Authentication & Security`: Panel user, Panel password (`Modify`).
  * `Interface Preferences`: Menu bar hidden items.
  * `Panel Setting`: IPv6, Offline mode, CDN Proxy, Home Bulletin switches.
