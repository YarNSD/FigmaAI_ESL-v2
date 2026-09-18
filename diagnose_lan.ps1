# ===============================================================================
#   🔍 ДИАГНОСТИКА СВЯЗИ СО ВТОРЫМ ПК ДЛЯ FIGMA-ПЛАГИНА (FigmaAI LAN)
# ===============================================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$TargetIP = "192.168.1.2"
$BridgePort = 45678
$WebPort = 3000

Write-Host ""
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "  🔍 ДИАГНОСТИКА СВЯЗИ С ОСНОВНЫМ ПК (192.168.1.2) ДЛЯ ПЛАГИНА FIGMA" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "  Целевой сервер: $TargetIP (Порты $BridgePort и $WebPort)"
Write-Host "  Время проверки: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""

$AllOk = $true
$NetworkOk = $true
$HttpOk = $true

# ── 1. ICMP Ping ─────────────────────────────────────────────────────────────
Write-Host "[1/6] Проверка физической связи (ICMP Ping)..." -ForegroundColor Yellow
try {
    $ping = Test-Connection -ComputerName $TargetIP -Count 2 -Quiet -ErrorAction Stop
    if ($ping) {
        Write-Host "      [OK] Пинг до $TargetIP проходит успешно!" -ForegroundColor Green
    } else {
        Write-Host "      [FAIL] $TargetIP не отвечает на пинг! Проверьте сеть Wi-Fi/кабель." -ForegroundColor Red
        $NetworkOk = $false
        $AllOk = $false
    }
} catch {
    Write-Host "      [FAIL] Ошибка пинга: $($_.Exception.Message)" -ForegroundColor Red
    $NetworkOk = $false
    $AllOk = $false
}
Write-Host ""

# ── 2. TCP Port 45678 ────────────────────────────────────────────────────────
Write-Host "[2/6] Проверка TCP-порта $BridgePort (Figma Bridge)..." -ForegroundColor Yellow
$client = New-Object System.Net.Sockets.TcpClient
try {
    $async = $client.BeginConnect($TargetIP, $BridgePort, $null, $null)
    $success = $async.AsyncWaitHandle.WaitOne(3000, $false)
    if ($success -and $client.Connected) {
        $client.EndConnect($async)
        Write-Host "      [OK] TCP-порт $BridgePort открыт и принимает подключения!" -ForegroundColor Green
    } else {
        Write-Host "      [FAIL] Не удалось подключиться к порту ${BridgePort} (Таймаут или Connection Refused)!" -ForegroundColor Red
        $NetworkOk = $false
        $AllOk = $false
    }
} catch {
    Write-Host "      [FAIL] Ошибка подключения к порту ${BridgePort}: $($_.Exception.Message)" -ForegroundColor Red
    $NetworkOk = $false
    $AllOk = $false
} finally {
    $client.Close()
}
Write-Host ""

# ── 3. TCP Port 3000 ─────────────────────────────────────────────────────────
Write-Host "[3/6] Проверка TCP-порта $WebPort (Web API)..." -ForegroundColor Yellow
$client2 = New-Object System.Net.Sockets.TcpClient
try {
    $async2 = $client2.BeginConnect($TargetIP, $WebPort, $null, $null)
    $success2 = $async2.AsyncWaitHandle.WaitOne(3000, $false)
    if ($success2 -and $client2.Connected) {
        $client2.EndConnect($async2)
        Write-Host "      [OK] TCP-порт $WebPort открыт и принимает подключения!" -ForegroundColor Green
    } else {
        Write-Host "      [FAIL] Не удалось подключиться к порту ${WebPort}!" -ForegroundColor Red
        $NetworkOk = $false
        $AllOk = $false
    }
} catch {
    Write-Host "      [FAIL] Ошибка подключения к порту ${WebPort}: $($_.Exception.Message)" -ForegroundColor Red
    $NetworkOk = $false
    $AllOk = $false
} finally {
    $client2.Close()
}
Write-Host ""

# ── 4. HTTP GET /status ──────────────────────────────────────────────────────
Write-Host "[4/6] Проверка HTTP GET http://${TargetIP}:${BridgePort}/status..." -ForegroundColor Yellow
try {
    $req = [System.Net.HttpWebRequest]::Create("http://${TargetIP}:${BridgePort}/status")
    $req.Timeout = 4000
    $resp = $req.GetResponse()
    $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
    $body = $reader.ReadToEnd()
    $resp.Close()
    Write-Host "      [OK] Ответ получен: $body" -ForegroundColor Green
} catch {
    Write-Host "      [FAIL] Ошибка HTTP GET: $($_.Exception.Message)" -ForegroundColor Red
    $HttpOk = $false
    $AllOk = $false
}
Write-Host ""

# ── 5. HTTP POST /poll (запрос плагина) ───────────────────────────────────────
Write-Host "[5/6] Проверка HTTP POST http://${TargetIP}:${BridgePort}/poll (запрос плагина)..." -ForegroundColor Yellow
try {
    $req = [System.Net.HttpWebRequest]::Create("http://${TargetIP}:${BridgePort}/poll")
    $req.Method = "POST"
    $req.ContentType = "application/json"
    $req.Timeout = 4000
    $payload = '{"tab_id":"diagnose_script","title":"LAN Test"}'
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    $req.ContentLength = $bytes.Length
    $stream = $req.GetRequestStream()
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Close()
    $resp = $req.GetResponse()
    $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
    $body = $reader.ReadToEnd()
    $resp.Close()
    Write-Host "      [OK] POST /poll успешен! Ответ: $body" -ForegroundColor Green
} catch {
    Write-Host "      [FAIL] Ошибка при POST /poll: $($_.Exception.Message)" -ForegroundColor Red
    $HttpOk = $false
    $AllOk = $false
}
Write-Host ""

# ── 6. Проверка manifest.json ────────────────────────────────────────────────
Write-Host "[6/6] Проверка безопасности манифеста (manifest.json)..." -ForegroundColor Yellow
$manifestFound = $false
$manifestAllowed = $false
$searchPaths = @(".", ".\figma_plugin", "..", "$PSScriptRoot", "$PSScriptRoot\figma_plugin")

foreach ($p in $searchPaths) {
    $mfPath = Join-Path $p "manifest.json"
    if (Test-Path $mfPath) {
        $manifestFound = $true
        $content = Get-Content $mfPath -Raw
        if ($content -match "\*" -or $content -match "192\.168") {
            $manifestAllowed = $true
            Write-Host "      [OK] Найден: $mfPath" -ForegroundColor Green
            Write-Host "      [OK] В allowedDomains разрешен доступ ко всем ресурсам ['*']!" -ForegroundColor Green
        } else {
            Write-Host "      [ОШИБКА НАЙДЕНА!] Файл: $mfPath" -ForegroundColor Red
            Write-Host "      В манифесте НЕТ разрешения на доступ к 192.168.x.x!" -ForegroundColor Red
            Write-Host "      Figma Desktop блокирует любые сетевые запросы, если домен не указан в manifest.json!" -ForegroundColor Red
        }
        break
    }
}

if (-not $manifestFound) {
    Write-Host "      [i] manifest.json не найден в каталоге скрипта." -ForegroundColor Gray
    Write-Host "      Поместите этот скрипт рядом с файлами плагина (manifest.json, code.js, ui.html)." -ForegroundColor Gray
}
Write-Host ""

# ── Проверка системного прокси ───────────────────────────────────────────────
Write-Host "-------------------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "Проверка системного прокси Windows:" -ForegroundColor DarkGray
$proxyReg = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction SilentlyContinue
if ($proxyReg -and $proxyReg.ProxyEnable -eq 1) {
    Write-Host "      [ВНИМАНИЕ] В Windows включен системный прокси: $($proxyReg.ProxyServer)" -ForegroundColor Yellow
    Write-Host "      Убедитесь, что для локальных адресов 192.168.1.* прокси отключен." -ForegroundColor Yellow
} else {
    Write-Host "      [OK] Системный прокси Windows выключен." -ForegroundColor Green
}
Write-Host "-------------------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# ── Итоговый отчет ───────────────────────────────────────────────────────────
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "  📊 ИТОГОВЫЙ РЕЗУЛЬТАТ ДИАГНОСТИКИ:" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan

if ($NetworkOk -and $HttpOk) {
    Write-Host "  ✅ СЕТЬ И СЕРВЕР РАБОТАЮТ НА 100%! Все запросы с этого ПК доходят до сервера." -ForegroundColor Green
    Write-Host ""
    if (-not $manifestAllowed) {
        Write-Host "  🎯 ПРИЧИНА СТАТУСА 'ОФЛАЙН' В FIGMA НАЙДЕНА:" -ForegroundColor Red
        Write-Host "  В Figma Desktop встроена песочница безопасности." -ForegroundColor Yellow
        Write-Host "  Плагин НЕ ИМЕЕТ ПРАВА отправлять сетевые запросы на адрес 192.168.1.2," -ForegroundColor Yellow
        Write-Host "  если этот IP не вписан в devAllowedDomains файла manifest.json!" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  🛠️ РЕШЕНИЕ (займет 1 минуту):" -ForegroundColor Cyan
        Write-Host "  1. Скопируйте обновленный manifest.json с основного ПК (или откройте manifest.json в блокноте)."
        Write-Host "  2. Убедитесь, что в блоке devAllowedDomains указаны:"
        Write-Host '     "http://192.168.1.2:45678", "http://192.168.1.2:3000", "http://192.168.*", "http://*"'
        Write-Host "  3. В Figma нажмите Ctrl + Alt + P (перезапустить плагин)."
        Write-Host "  4. Плагин моментально загорится зелёным ONLINE!" -ForegroundColor Green
    } else {
        Write-Host "  Манифест настроен правильно. Если плагин всё ещё офлайн:" -ForegroundColor Yellow
        Write-Host "  В окне плагина нажмите ⚙️ -> [192.168.1.2] -> [Сохранить] -> Перезапустите плагин."
    }
} else {
    Write-Host "  ❌ ОБНАРУЖЕНЫ ПРОБЛЕМЫ С СЕТЕВЫМ ПОДКЛЮЧЕНИЕМ." -ForegroundColor Red
    Write-Host "  Проверьте, что основной ПК включен, а его IP-адрес равен 192.168.1.2." -ForegroundColor Yellow
}
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Нажмите Enter для завершения..."
