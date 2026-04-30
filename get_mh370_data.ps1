# MH370 Data Fetcher — fetches 2014-03-07 data from INTERMAGNET
# Run from: C:\Users\Mike\uap_sniffer\uap_sniffer

Write-Host "Fetching MH370 magnetometer data for 2014-03-07..."

$base = "https://imag-data.bgs.ac.uk/GIN_V1/GINServices?Request=GetData&samplesPerDay=1440&startDate=2014-03-07&endDate=2014-03-08&dataType=definitive&orientation=XYZF&format=IAGA2002"

Invoke-WebRequest "$base&observatoryIagaCode=CNB" -OutFile "event_outputs\MH370_2014\CNB_20140307.min"
Write-Host "CNB done"

Invoke-WebRequest "$base&observatoryIagaCode=KNY" -OutFile "event_outputs\MH370_2014\KNY_20140307.min"
Write-Host "KNY done"

Invoke-WebRequest "$base&observatoryIagaCode=KAK" -OutFile "event_outputs\MH370_2014\KAK_20140307.min"
Write-Host "KAK done"

# Verify dates
Write-Host "`nVerifying dates in downloaded files..."
$files = @("CNB_20140307.min","KNY_20140307.min","KAK_20140307.min")
foreach ($file in $files) {
    $path = "event_outputs\MH370_2014\$file"
    $lines = Get-Content $path -TotalCount 30
    $dataline = $lines | Where-Object { $_ -match "^2014" } | Select-Object -First 1
    if ($dataline) {
        Write-Host "OK $file — $($dataline.Substring(0,[Math]::Min(40,$dataline.Length)))"
    } else {
        $wrongline = $lines | Where-Object { $_ -match "^\d{4}-" } | Select-Object -First 1
        Write-Host "WRONG DATE $file — got: $($wrongline.Substring(0,[Math]::Min(40,$wrongline.Length)))"
    }
}

Write-Host "`nRunning analysis..."
python read_local_mag.py

Write-Host "`nOpening plot..."
Start-Process "event_outputs\MH370_2014\MH370_local_mag.png"
