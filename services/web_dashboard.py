import csv
import hashlib
import hmac
import html
import io
import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from aiohttp import web

from config import settings
from database.db import db

logger = logging.getLogger(__name__)

COOKIE_NAME = "trivela_admin_session"
SESSION_MAX_AGE = 14 * 86400  # 14 days in seconds


# ---------------------------------------------------------
# AUTHENTICATION & SESSION HELPERS
# ---------------------------------------------------------

def sign_session(user_id: int) -> str:
    """Creates a cryptographically signed session cookie value: user_id:timestamp:signature."""
    ts = int(time.time())
    payload = f"{user_id}:{ts}"
    signature = hmac.new(
        settings.dashboard_session_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{signature}"


def verify_session(request: web.Request) -> Optional[int]:
    """
    Verifies the session cookie from request.
    Returns user_id (int) if valid, unexpired, and listed in ADMIN_IDS; otherwise None.
    """
    cookie_val = request.cookies.get(COOKIE_NAME)
    if not cookie_val:
        return None

    parts = cookie_val.split(":")
    if len(parts) != 3:
        return None

    user_id_str, ts_str, received_sig = parts

    try:
        user_id = int(user_id_str)
        ts = int(ts_str)
    except ValueError:
        return None

    # Check expiration (14 days) and clock skew
    now = int(time.time())
    if now - ts > SESSION_MAX_AGE or now - ts < -60:
        return None

    # Verify HMAC signature
    expected_payload = f"{user_id}:{ts}"
    expected_sig = hmac.new(
        settings.dashboard_session_secret.encode("utf-8"),
        expected_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(received_sig, expected_sig):
        return None

    # Must be in admin_ids_list
    if user_id not in settings.admin_ids_list:
        return None

    return user_id


# ---------------------------------------------------------
# HTML TEMPLATE RENDERING
# ---------------------------------------------------------

def render_base_layout(
    title: str,
    active_tab: str,
    user_id: Optional[int],
    content_html: str,
    extra_scripts: str = "",
) -> str:
    """Base HTML layout wrapping all admin pages with modern dark UI, navbar, and CDNs."""
    user_badge = (
        f'<span class="badge bg-secondary me-2"><i class="bi bi-shield-lock me-1"></i>ID {user_id}</span>'
        f'<a href="/logout" class="btn btn-sm btn-outline-danger"><i class="bi bi-box-arrow-right me-1"></i>Выйти</a>'
        if user_id
        else ""
    )

    nav_items = [
        ("/", "dashboard", '<i class="bi bi-speedometer2 me-1"></i> Дашборд'),
        ("/payments", "payments", '<i class="bi bi-credit-card me-1"></i> Платежи'),
        ("/generations", "generations", '<i class="bi bi-music-note-beamed me-1"></i> Генерации'),
        ("/users", "users", '<i class="bi bi-people me-1"></i> Пользователи'),
    ]

    nav_links_html = ""
    for path, tab_key, label in nav_items:
        active_class = "active fw-bold text-white border-bottom border-2 border-primary" if active_tab == tab_key else "text-light-50"
        nav_links_html += f'<li class="nav-item"><a class="nav-link {active_class} px-3" href="{path}">{label}</a></li>\n'

    return f"""<!DOCTYPE html>
<html lang="ru" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} — Trivela Music Admin</title>
    <!-- Bootstrap 5.3 CSS -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    <!-- Bootstrap Icons -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <!-- DataTables Bootstrap 5 CSS -->
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.8/css/dataTables.bootstrap5.min.css">
    <style>
        body {{
            background-color: #0b0f19;
            color: #f3f4f6;
            font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            min-height: 100vh;
        }}
        .navbar-custom {{
            background: linear-gradient(180deg, #111827 0%, rgba(17, 24, 39, 0.95) 100%);
            border-bottom: 1px solid #1f2937;
            backdrop-filter: blur(8px);
        }}
        .card-custom {{
            background-color: #111827;
            border: 1px solid #1f2937;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}
        .card-custom:hover {{
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
        }}
        .brand-gradient {{
            background: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
        }}
        .kpi-title {{
            color: #9ca3af;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.25rem;
        }}
        .kpi-value {{
            font-size: 1.85rem;
            font-weight: 700;
            color: #ffffff;
        }}
        .kpi-subtext {{
            font-size: 0.8rem;
            color: #9ca3af;
        }}
        .table-custom {{
            --bs-table-bg: transparent;
            --bs-table-color: #e5e7eb;
            --bs-table-border-color: #1f2937;
            vertical-align: middle;
        }}
        .table-custom tbody tr:hover {{
            background-color: rgba(255, 255, 255, 0.02) !important;
        }}
        .dataTables_wrapper .dataTables_paginate .paginate_button.active .page-link {{
            background-color: #6366f1;
            border-color: #6366f1;
        }}
        .dataTables_wrapper .dataTables_paginate .page-link {{
            background-color: #1f2937;
            border-color: #374151;
            color: #e5e7eb;
        }}
        audio {{
            filter: invert(1) hue-rotate(180deg);
        }}
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark navbar-custom sticky-top">
        <div class="container-fluid px-4">
            <a class="navbar-brand d-flex align-items-center gap-2" href="/">
                <span class="fs-4">🎵</span>
                <span class="brand-gradient fs-5">TRIVELA MUSIC</span>
                <span class="badge bg-dark border border-secondary text-light ms-1" style="font-size: 0.65rem;">ADMIN</span>
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#adminNavbar">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="adminNavbar">
                <ul class="navbar-nav me-auto mb-2 mb-lg-0">
                    {nav_links_html}
                </ul>
                <div class="d-flex align-items-center">
                    {user_badge}
                </div>
            </div>
        </div>
    </nav>

    <main class="container-fluid px-4 py-4">
        {content_html}
    </main>

    <footer class="container-fluid px-4 py-3 text-center text-muted border-top border-dark mt-5" style="font-size: 0.8rem;">
        <div>Trivela Music Bot Web Dashboard &copy; {datetime.now().year} &bull; Версия 2.0</div>
    </footer>

    <!-- jQuery & Bootstrap Bundle -->
    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    <!-- DataTables JS -->
    <script src="https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.8/js/dataTables.bootstrap5.min.js"></script>
    <!-- Chart.js 4 -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script>
        // Russian localization for all DataTables
        const ruDataTablesLang = {{
            search: "Поиск:",
            searchPlaceholder: "Фильтр...",
            lengthMenu: "Показывать _MENU_ строк",
            info: "Строки с _START_ по _END_ из _TOTAL_",
            infoEmpty: "Строки с 0 по 0 из 0",
            infoFiltered: "(отфильтровано из _MAX_)",
            zeroRecords: "Ничего не найдено",
            paginate: {{
                first: "«",
                previous: "Назад",
                next: "Вперёд",
                last: "»"
            }}
        }};
    </script>
    {extra_scripts}
</body>
</html>
"""


def render_dashboard_page(stats: Dict[str, Any], chart_data: Dict[str, Any], user_id: int) -> str:
    """Renders the main dashboard page with KPI cards and 14-day interactive Chart.js charts."""
    rev_total = f"{stats.get('revenue_total', 0):,.0f} ₽".replace(",", " ")
    rev_today = f"{stats.get('revenue_today', 0):,.0f} ₽".replace(",", " ")
    rev_7d = f"{stats.get('revenue_7d', 0):,.0f} ₽".replace(",", " ")
    rev_30d = f"{stats.get('revenue_30d', 0):,.0f} ₽".replace(",", " ")

    pay_total = stats.get("payments_count_total", 0)
    pay_today = stats.get("payments_count_today", 0)
    pay_7d = stats.get("payments_count_7d", 0)
    avg_check = f"{stats.get('avg_check', 0):,.1f} ₽".replace(",", " ")

    gens_total = stats.get("generations_total", 0)
    gens_success = stats.get("generations_success", 0)
    gens_failure = stats.get("generations_failure", 0)
    gens_today = stats.get("generations_today", 0)
    gens_success_pct = round((gens_success / gens_total * 100), 1) if gens_total > 0 else 0.0

    users_total = stats.get("users_total", 0)
    users_today = stats.get("users_today", 0)
    buyers_total = stats.get("buyers_total", 0)
    conversion_rate = stats.get("conversion_rate", 0.0)

    # JSON for charts
    labels_json = json.dumps(chart_data.get("labels", []))
    revenue_series_json = json.dumps(chart_data.get("revenue", []))
    gens_series_json = json.dumps(chart_data.get("generations", []))

    content = f"""
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h2 class="h3 fw-bold mb-1">Сводная аналитика</h2>
            <p class="text-muted mb-0">Ключевые показатели работы бота, продаж и генераций музыки</p>
        </div>
        <div class="d-flex gap-2">
            <a href="/payments" class="btn btn-outline-primary btn-sm"><i class="bi bi-credit-card me-1"></i>Все платежи</a>
            <a href="/generations" class="btn btn-outline-info btn-sm"><i class="bi bi-music-note me-1"></i>Все треки</a>
        </div>
    </div>

    <!-- KPI CARDS GRID -->
    <div class="row g-3 mb-4">
        <!-- KPI 1: Revenue -->
        <div class="col-12 col-sm-6 col-xl-3">
            <div class="card card-custom p-3 h-100">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <div class="kpi-title"><i class="bi bi-wallet2 me-1 text-success"></i>Выручка (всего)</div>
                        <div class="kpi-value text-success">{rev_total}</div>
                    </div>
                    <span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="bi bi-graph-up-arrow"></i></span>
                </div>
                <div class="kpi-subtext mt-2 pt-2 border-top border-dark">
                    <span>Сегодня: <strong class="text-white">{rev_today}</strong></span> &bull; 
                    <span>7д: <strong class="text-white">{rev_7d}</strong></span> &bull; 
                    <span>30д: <strong class="text-white">{rev_30d}</strong></span>
                </div>
            </div>
        </div>

        <!-- KPI 2: Payments Count & Avg Check -->
        <div class="col-12 col-sm-6 col-xl-3">
            <div class="card card-custom p-3 h-100">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <div class="kpi-title"><i class="bi bi-receipt me-1 text-primary"></i>Оплачено заказов</div>
                        <div class="kpi-value text-primary">{pay_total}</div>
                    </div>
                    <span class="badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1"><i class="bi bi-check2-circle"></i></span>
                </div>
                <div class="kpi-subtext mt-2 pt-2 border-top border-dark">
                    <span>Сегодня: <strong class="text-white">+{pay_today}</strong></span> &bull; 
                    <span>7д: <strong class="text-white">+{pay_7d}</strong></span> &bull; 
                    <span>Ср. чек: <strong class="text-white">{avg_check}</strong></span>
                </div>
            </div>
        </div>

        <!-- KPI 3: Music Generations -->
        <div class="col-12 col-sm-6 col-xl-3">
            <div class="card card-custom p-3 h-100">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <div class="kpi-title"><i class="bi bi-music-note-beamed me-1 text-info"></i>Генераций музыки</div>
                        <div class="kpi-value text-info">{gens_total}</div>
                    </div>
                    <span class="badge bg-info-subtle text-info border border-info-subtle px-2 py-1">{gens_success_pct}% OK</span>
                </div>
                <div class="kpi-subtext mt-2 pt-2 border-top border-dark">
                    <span>Успешно: <strong class="text-success">{gens_success}</strong></span> &bull; 
                    <span>Ошибок: <strong class="text-danger">{gens_failure}</strong></span> &bull; 
                    <span>Сегодня: <strong class="text-white">+{gens_today}</strong></span>
                </div>
            </div>
        </div>

        <!-- KPI 4: Users & Conversion -->
        <div class="col-12 col-sm-6 col-xl-3">
            <div class="card card-custom p-3 h-100">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <div class="kpi-title"><i class="bi bi-people me-1 text-warning"></i>Пользователи</div>
                        <div class="kpi-value text-warning">{users_total}</div>
                    </div>
                    <span class="badge bg-warning-subtle text-warning border border-warning-subtle px-2 py-1">{conversion_rate}% Платят</span>
                </div>
                <div class="kpi-subtext mt-2 pt-2 border-top border-dark">
                    <span>Новых сегодня: <strong class="text-white">+{users_today}</strong></span> &bull; 
                    <span>Покупателей: <strong class="text-white">{buyers_total}</strong></span>
                </div>
            </div>
        </div>
    </div>

    <!-- CHARTS SECTION -->
    <div class="row g-4 mb-4">
        <!-- Chart 1: Daily Revenue -->
        <div class="col-12 col-lg-6">
            <div class="card card-custom p-4 h-100">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="card-title fw-bold mb-0"><i class="bi bi-cash-stack me-2 text-success"></i>Динамика выручки (последние 14 дней)</h5>
                    <span class="badge bg-dark border border-secondary text-muted">в рублях (₽)</span>
                </div>
                <div style="position: relative; height: 260px; width: 100%;">
                    <canvas id="revenueChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Chart 2: Daily Generations -->
        <div class="col-12 col-lg-6">
            <div class="card card-custom p-4 h-100">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="card-title fw-bold mb-0"><i class="bi bi-soundwave me-2 text-info"></i>Активность генераций (последние 14 дней)</h5>
                    <span class="badge bg-dark border border-secondary text-muted">треков в день</span>
                </div>
                <div style="position: relative; height: 260px; width: 100%;">
                    <canvas id="generationsChart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <!-- SYSTEM STATUS STRIP -->
    <div class="card card-custom p-3">
        <div class="row align-items-center text-center text-md-start g-3">
            <div class="col-12 col-md-4">
                <span class="text-muted"><i class="bi bi-hdd-network me-1"></i>Сервер:</span>
                <span class="fw-semibold text-white">{settings.dashboard_base_url}</span>
            </div>
            <div class="col-12 col-md-4 text-center">
                <span class="badge bg-success-subtle text-success border border-success me-2">● Активен</span>
                <span class="text-muted">Порт {settings.dashboard_port} &bull; Вебхук YooKassa: {'Включен' if settings.webhook_enabled else 'Через поллер'}</span>
            </div>
            <div class="col-12 col-md-4 text-md-end">
                <span class="text-muted"><i class="bi bi-clock me-1"></i>Время сервера (МСК):</span>
                <span class="fw-semibold text-white">{datetime.now().strftime('%d.%m.%Y %H:%M')}</span>
            </div>
        </div>
    </div>
    """

    extra_scripts = f"""
    <script>
        const chartLabels = {labels_json};
        const revData = {revenue_series_json};
        const gensData = {gens_series_json};

        // Revenue Chart (Gradient Line)
        const ctxRev = document.getElementById('revenueChart').getContext('2d');
        const gradientRev = ctxRev.createLinearGradient(0, 0, 0, 260);
        gradientRev.addColorStop(0, 'rgba(34, 197, 94, 0.4)');
        gradientRev.addColorStop(1, 'rgba(34, 197, 94, 0.0)');

        new Chart(ctxRev, {{
            type: 'line',
            data: {{
                labels: chartLabels,
                datasets: [{{
                    label: 'Выручка (₽)',
                    data: revData,
                    borderColor: '#22c55e',
                    backgroundColor: gradientRev,
                    borderWidth: 2.5,
                    pointBackgroundColor: '#22c55e',
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    fill: true,
                    tension: 0.3
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                return context.parsed.y.toLocaleString('ru-RU') + ' ₽';
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        grid: {{ color: '#1f2937' }},
                        ticks: {{
                            color: '#9ca3af',
                            callback: function(val) {{ return val + ' ₽'; }}
                        }}
                    }},
                    x: {{
                        grid: {{ display: false }},
                        ticks: {{ color: '#9ca3af' }}
                    }}
                }}
            }}
        }});

        // Generations Chart (Bar)
        const ctxGens = document.getElementById('generationsChart').getContext('2d');
        new Chart(ctxGens, {{
            type: 'bar',
            data: {{
                labels: chartLabels,
                datasets: [{{
                    label: 'Создано треков',
                    data: gensData,
                    backgroundColor: '#6366f1',
                    borderRadius: 6,
                    hoverBackgroundColor: '#818cf8',
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        grid: {{ color: '#1f2937' }},
                        ticks: {{
                            color: '#9ca3af',
                            stepSize: 1
                        }}
                    }},
                    x: {{
                        grid: {{ display: false }},
                        ticks: {{ color: '#9ca3af' }}
                    }}
                }}
            }}
        }});
    </script>
    """

    return render_base_layout("Дашборд", "dashboard", user_id, content, extra_scripts)


def render_payments_page(payments: List[Dict[str, Any]], user_id: int) -> str:
    """Renders the payments table page with DataTables sorting, searching, and CSV export."""
    rows_html = ""
    for p in payments:
        pid = p.get("id")
        created_at = p.get("created_at") or ""
        # Clean up timestamp display (YYYY-MM-DD HH:MM)
        date_str = created_at[:16].replace("T", " ") if created_at else "—"

        uname = f"@{html.escape(p['username'])}" if p.get("username") else (
            html.escape(p.get("first_name") or "") if p.get("first_name") else f"ID {p['user_id']}"
        )
        user_info = f'<a href="https://t.me/{p.get("username")}" target="_blank" class="text-decoration-none text-light fw-medium">{uname}</a><div class="text-muted" style="font-size:0.75rem;">ID {p["user_id"]}</div>' if p.get("username") else f'<span class="text-light fw-medium">{uname}</span>'

        amount = f"{p.get('amount', 0):,.0f} ₽".replace(",", " ")
        credits = f"+{p.get('credits', 0)}"

        promo = f'<span class="badge bg-info-subtle text-info border border-info-subtle">{html.escape(p["promo_code"])}</span>' if p.get("promo_code") else '<span class="text-muted">—</span>'

        status = p.get("status", "")
        if status == "succeeded":
            status_badge = '<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>Оплачен</span>'
        elif status == "pending":
            status_badge = '<span class="badge bg-warning text-dark"><i class="bi bi-clock me-1"></i>Ожидает</span>'
        elif status == "canceled":
            status_badge = '<span class="badge bg-danger"><i class="bi bi-x-circle me-1"></i>Отменён</span>'
        else:
            status_badge = f'<span class="badge bg-secondary">{html.escape(status)}</span>'

        yk_id = p.get("payment_id") or "—"
        yk_short = (yk_id[:8] + "..." + yk_id[-4:]) if len(yk_id) > 14 else yk_id

        rows_html += f"""
        <tr>
            <td class="text-muted fw-bold">#{pid}</td>
            <td>{date_str}</td>
            <td>{user_info}</td>
            <td class="fw-bold text-success">{amount}</td>
            <td><span class="badge bg-dark border border-secondary">{credits} треков</span></td>
            <td>{promo}</td>
            <td>{status_badge}</td>
            <td><code class="text-muted" style="font-size: 0.75rem;" title="{html.escape(yk_id)}">{html.escape(yk_short)}</code></td>
        </tr>
        """

    content = f"""
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h2 class="h3 fw-bold mb-1">История платежей</h2>
            <p class="text-muted mb-0">Все транзакции YooKassa с возможностью поиска, фильтрации и выгрузки</p>
        </div>
        <div>
            <a href="/payments/export.csv" class="btn btn-success btn-sm"><i class="bi bi-file-earmark-spreadsheet me-1"></i>Скачать CSV</a>
        </div>
    </div>

    <div class="card card-custom p-4">
        <div class="table-responsive">
            <table id="paymentsTable" class="table table-custom align-middle">
                <thead>
                    <tr>
                        <th style="width: 50px;">ID</th>
                        <th>Дата (МСК)</th>
                        <th>Пользователь</th>
                        <th>Сумма</th>
                        <th>Пакет</th>
                        <th>Промокод</th>
                        <th>Статус</th>
                        <th>YooKassa ID</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
    """

    extra_scripts = """
    <script>
        $(document).ready(function() {
            $('#paymentsTable').DataTable({
                order: [[0, 'desc']],
                pageLength: 25,
                language: ruDataTablesLang
            });
        });
    </script>
    """

    return render_base_layout("Платежи", "payments", user_id, content, extra_scripts)


def render_generations_page(generations: List[Dict[str, Any]], user_id: int) -> str:
    """Renders the generations history page with inline audio players."""
    rows_html = ""
    for g in generations:
        gid = g.get("id")
        created_at = g.get("created_at") or ""
        date_str = created_at[:16].replace("T", " ") if created_at else "—"

        uname = f"@{html.escape(g['username'])}" if g.get("username") else (
            html.escape(g.get("first_name") or "") if g.get("first_name") else f"ID {g['user_id']}"
        )
        user_info = f'<a href="https://t.me/{g.get("username")}" target="_blank" class="text-decoration-none text-light">{uname}</a>' if g.get("username") else f'<span class="text-light">{uname}</span>'

        artist = html.escape(g.get("artist") or "")
        genres = html.escape(g.get("genres") or "")

        style_info = ""
        if artist:
            style_info += f'<span class="badge bg-primary-subtle text-primary border border-primary-subtle me-1"><i class="bi bi-mic me-1"></i>{artist}</span>'
        if genres:
            style_info += f'<span class="badge bg-secondary-subtle text-light border border-secondary">{genres}</span>'
        if not style_info:
            style_info = '<span class="text-muted">—</span>'

        prompt = html.escape(g.get("prompt") or "")
        prompt_short = (prompt[:60] + "...") if len(prompt) > 60 else (prompt or "—")

        mode = '<span class="badge bg-secondary">Инструментал</span>' if g.get("instrumental") else '<span class="badge bg-dark border">С вокалом</span>'

        status = g.get("status") or ""
        if status == "SUCCESS":
            status_badge = '<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>Готово</span>'
        elif status == "FAILURE":
            status_badge = '<span class="badge bg-danger"><i class="bi bi-x-circle me-1"></i>Ошибка</span>'
        else:
            status_badge = f'<span class="badge bg-warning text-dark">{html.escape(status)}</span>'

        audio_url = g.get("audio_url")
        if audio_url:
            player_html = f"""
            <div class="d-flex align-items-center gap-2">
                <audio controls preload="none" style="height: 32px; width: 200px;" src="{html.escape(audio_url)}"></audio>
                <a href="{html.escape(audio_url)}" target="_blank" class="btn btn-sm btn-outline-secondary" title="Открыть/Скачать"><i class="bi bi-box-arrow-up-right"></i></a>
            </div>
            """
        else:
            player_html = '<span class="text-muted">—</span>'

        rows_html += f"""
        <tr>
            <td class="text-muted fw-bold">#{gid}</td>
            <td>{date_str}</td>
            <td>{user_info}</td>
            <td>{style_info}</td>
            <td><span title="{prompt}">{prompt_short}</span></td>
            <td>{mode}</td>
            <td>{status_badge}</td>
            <td>{player_html}</td>
        </tr>
        """

    content = f"""
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h2 class="h3 fw-bold mb-1">История генераций</h2>
            <p class="text-muted mb-0">Все созданные композиции с возможностью прослушивания треков прямо в браузере</p>
        </div>
    </div>

    <div class="card card-custom p-4">
        <div class="table-responsive">
            <table id="generationsTable" class="table table-custom align-middle">
                <thead>
                    <tr>
                        <th style="width: 50px;">ID</th>
                        <th>Дата (МСК)</th>
                        <th>Пользователь</th>
                        <th>Артист / Жанры</th>
                        <th>Описание / Промт</th>
                        <th>Режим</th>
                        <th>Статус</th>
                        <th style="min-width: 250px;">Аудиоплеер</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
    """

    extra_scripts = """
    <script>
        $(document).ready(function() {
            $('#generationsTable').DataTable({
                order: [[0, 'desc']],
                pageLength: 25,
                language: ruDataTablesLang
            });
        });
    </script>
    """

    return render_base_layout("Генерации", "generations", user_id, content, extra_scripts)


def render_users_page(users: List[Dict[str, Any]], user_id: int) -> str:
    """Renders the users table with balances and spending metrics."""
    rows_html = ""
    for u in users:
        uid = u.get("user_id")
        created_at = u.get("created_at") or ""
        date_str = created_at[:10] if created_at else "—"

        uname = f"@{html.escape(u['username'])}" if u.get("username") else (
            html.escape(u.get("first_name") or "") if u.get("first_name") else f"ID {uid}"
        )
        user_info = f'<a href="https://t.me/{u.get("username")}" target="_blank" class="text-decoration-none text-light fw-medium">{uname}</a>' if u.get("username") else f'<span class="text-light fw-medium">{uname}</span>'

        paid_bal = u.get("paid_balance", 0)
        gift_bal = u.get("gift_balance", 0)
        ref_bal = u.get("referral_balance", 0)

        total_spent = u.get("total_spent", 0)
        spent_badge = f'<strong class="text-success">{total_spent:,.0f} ₽</strong>'.replace(",", " ") if total_spent > 0 else '<span class="text-muted">0 ₽</span>'

        orders = u.get("successful_orders", 0)
        orders_badge = f'<span class="badge bg-success-subtle text-success border border-success-subtle">{orders}</span>' if orders > 0 else '<span class="text-muted">0</span>'

        gens = u.get("total_generations", 0)
        gens_badge = f'<span class="badge bg-info-subtle text-info border border-info-subtle">{gens}</span>' if gens > 0 else '<span class="text-muted">0</span>'

        rows_html += f"""
        <tr>
            <td class="text-muted"><code>{uid}</code></td>
            <td>{user_info}</td>
            <td><strong class="text-white">{paid_bal}</strong> <span class="text-muted">плат.</span></td>
            <td><span class="text-warning">{gift_bal}</span> <span class="text-muted">под.</span></td>
            <td><span class="text-info">{ref_bal}</span> <span class="text-muted">реф.</span></td>
            <td>{spent_badge}</td>
            <td>{orders_badge}</td>
            <td>{gens_badge}</td>
            <td class="text-muted">{date_str}</td>
        </tr>
        """

    content = f"""
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h2 class="h3 fw-bold mb-1">Пользователи бота</h2>
            <p class="text-muted mb-0">Балансы, суммарные траты и активность пользователей</p>
        </div>
    </div>

    <div class="card card-custom p-4">
        <div class="table-responsive">
            <table id="usersTable" class="table table-custom align-middle">
                <thead>
                    <tr>
                        <th>Telegram ID</th>
                        <th>Пользователь</th>
                        <th>Платный баланс</th>
                        <th>Подарочный баланс</th>
                        <th>Реферальный баланс</th>
                        <th>Всего оплачено</th>
                        <th>Покупок</th>
                        <th>Генераций</th>
                        <th>Регистрация</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
    """

    extra_scripts = """
    <script>
        $(document).ready(function() {
            $('#usersTable').DataTable({
                order: [[5, 'desc']], // Order by total_spent descending
                pageLength: 25,
                language: ruDataTablesLang
            });
        });
    </script>
    """

    return render_base_layout("Пользователи", "users", user_id, content, extra_scripts)


def render_login_page(bot_username: str = "") -> str:
    """Renders the login prompt page explaining magic link auth via Telegram."""
    bot_url = f"https://t.me/{bot_username}" if bot_username else "https://t.me"

    content = f"""
    <div class="row justify-content-center align-items-center" style="min-height: 70vh;">
        <div class="col-12 col-md-8 col-lg-5">
            <div class="card card-custom p-4 p-md-5 text-center">
                <div class="fs-1 mb-3">🔒</div>
                <h3 class="fw-bold mb-2">Вход в панель администратора</h3>
                <p class="text-muted mb-4">
                    Доступ к веб-панели разрешён только администраторам бота.
                </p>

                <div class="p-3 mb-4 rounded text-start" style="background-color: #1f2937; border: 1px solid #374151;">
                    <div class="fw-bold text-white mb-2"><i class="bi bi-info-circle me-1 text-primary"></i>Как войти:</div>
                    <ol class="text-light-50 ps-3 mb-0" style="font-size: 0.9rem;">
                        <li class="mb-1">Откройте Telegram-бота <strong>Trivela Music</strong>.</li>
                        <li class="mb-1">Отправьте команду <code>/admin</code>.</li>
                        <li class="mb-1">Нажмите кнопку <strong>«🌐 Веб-панель»</strong>.</li>
                        <li>Перейдите по полученной одноразовой ссылке.</li>
                    </ol>
                </div>

                <a href="{bot_url}" target="_blank" class="btn btn-primary w-100 py-2 fw-semibold">
                    <i class="bi bi-telegram me-2"></i>Перейти в Telegram
                </a>
            </div>
        </div>
    </div>
    """
    return render_base_layout("Вход", "", None, content)


def render_error_page(title: str, message: str) -> str:
    """Renders an error card."""
    content = f"""
    <div class="row justify-content-center align-items-center" style="min-height: 70vh;">
        <div class="col-12 col-md-7 col-lg-5">
            <div class="card card-custom p-4 p-md-5 text-center border-danger">
                <div class="fs-1 text-danger mb-3">⚠️</div>
                <h3 class="fw-bold mb-2">{html.escape(title)}</h3>
                <p class="text-muted mb-4">{html.escape(message)}</p>
                <a href="/login" class="btn btn-outline-light"><i class="bi bi-arrow-left me-1"></i>Вернуться ко входу</a>
            </div>
        </div>
    </div>
    """
    return render_base_layout("Ошибка", "", None, content)


# ---------------------------------------------------------
# AIOHTTP REQUEST HANDLERS
# ---------------------------------------------------------

async def handle_magic_auth(request: web.Request) -> web.Response:
    """
    GET /auth?token=<magic_token>
    Validates single-use token from Telegram, establishes signed session cookie, redirects to /.
    """
    token = request.query.get("token")
    if not token:
        return web.Response(
            text=render_error_page("Отсутствует токен", "В ссылке для входа отсутствует одноразовый ключ."),
            content_type="text/html",
            status=400,
        )

    user_id = await db.validate_and_consume_magic_token(token)
    if not user_id:
        return web.Response(
            text=render_error_page(
                "Ссылка недействительна",
                "Срок действия одноразовой ссылки истёк (10 минут) или она уже была использована. Пожалуйста, запросите новую ссылку в боте через /admin.",
            ),
            content_type="text/html",
            status=401,
        )

    if user_id not in settings.admin_ids_list:
        return web.Response(
            text=render_error_page("Доступ запрещён", "Ваш аккаунт не входит в список администраторов бота."),
            content_type="text/html",
            status=403,
        )

    # Establish session cookie valid for 14 days
    session_value = sign_session(user_id)
    response = web.HTTPFound(location="/")
    response.set_cookie(
        COOKIE_NAME,
        session_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="Lax",
        path="/",
    )
    logger.info("Admin %s logged into Web Dashboard via Magic Link", user_id)
    return response


async def handle_logout(request: web.Request) -> web.Response:
    """GET /logout - clears session cookie and redirects to /login."""
    response = web.HTTPFound(location="/login")
    response.del_cookie(COOKIE_NAME, path="/")
    return response


async def handle_login(request: web.Request) -> web.Response:
    """GET /login - shows login prompt or redirects if already authenticated."""
    user_id = verify_session(request)
    if user_id:
        raise web.HTTPFound(location="/")

    bot = request.app.get("bot")
    bot_username = ""
    if bot:
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username or ""
        except Exception:
            pass

    return web.Response(text=render_login_page(bot_username), content_type="text/html")


async def handle_dashboard(request: web.Request) -> web.Response:
    """GET / or GET /dashboard - renders main dashboard with KPI metrics and 14-day charts."""
    user_id = verify_session(request)
    if not user_id:
        raise web.HTTPFound(location="/login")

    stats = await db.get_detailed_dashboard_stats()
    chart_data = await db.get_daily_chart_data(days=14)

    html_content = render_dashboard_page(stats, chart_data, user_id)
    return web.Response(text=html_content, content_type="text/html")


async def handle_payments(request: web.Request) -> web.Response:
    """GET /payments - renders detailed payments history table."""
    user_id = verify_session(request)
    if not user_id:
        raise web.HTTPFound(location="/login")

    payments = await db.get_all_payments_detailed(limit=1000)
    html_content = render_payments_page(payments, user_id)
    return web.Response(text=html_content, content_type="text/html")


async def handle_payments_csv(request: web.Request) -> web.Response:
    """GET /payments/export.csv - exports all payments as CSV file with UTF-8 BOM."""
    user_id = verify_session(request)
    if not user_id:
        raise web.HTTPFound(location="/login")

    payments = await db.get_all_payments_detailed(limit=5000)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ID",
        "YooKassa ID",
        "Telegram User ID",
        "Имя / Username",
        "Сумма (₽)",
        "Кредиты",
        "Промокод",
        "Статус",
        "Дата создания (МСК)",
    ])

    for p in payments:
        uname = f"@{p['username']}" if p.get("username") else (p.get("first_name") or f"ID {p['user_id']}")
        status_map = {
            "succeeded": "Оплачен",
            "pending": "Ожидает",
            "canceled": "Отменён",
        }
        st_ru = status_map.get(p.get("status"), p.get("status"))
        writer.writerow([
            p.get("id"),
            p.get("payment_id") or "",
            p.get("user_id"),
            uname,
            p.get("amount") or 0,
            p.get("credits") or 0,
            p.get("promo_code") or "",
            st_ru,
            p.get("created_at") or "",
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    filename = f"trivela_payments_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    return web.Response(
        body=csv_bytes,
        content_type="text/csv",
        charset="utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


async def handle_generations(request: web.Request) -> web.Response:
    """GET /generations - renders music generations history table."""
    user_id = verify_session(request)
    if not user_id:
        raise web.HTTPFound(location="/login")

    generations = await db.get_all_generations_detailed(limit=1000)
    html_content = render_generations_page(generations, user_id)
    return web.Response(text=html_content, content_type="text/html")


async def handle_users(request: web.Request) -> web.Response:
    """GET /users - renders users table with balances and total spend."""
    user_id = verify_session(request)
    if not user_id:
        raise web.HTTPFound(location="/login")

    users = await db.get_all_users_detailed(limit=1000)
    html_content = render_users_page(users, user_id)
    return web.Response(text=html_content, content_type="text/html")


def register_dashboard_routes(app: web.Application) -> None:
    """Registers all dashboard routes to the aiohttp application."""
    app.router.add_get("/", handle_dashboard)
    app.router.add_get("/dashboard", handle_dashboard)
    app.router.add_get("/payments", handle_payments)
    app.router.add_get("/payments/export.csv", handle_payments_csv)
    app.router.add_get("/generations", handle_generations)
    app.router.add_get("/users", handle_users)
    app.router.add_get("/auth", handle_magic_auth)
    app.router.add_get("/login", handle_login)
    app.router.add_get("/logout", handle_logout)
