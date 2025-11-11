param(
    [string]$Topic = "creditcard_stream",
    [string]$Bootstrap = "localhost:9092",
    [int]$Partitions = 1,
    [int]$Replication = 1,
    [string]$ContainerName = "kafka"
)

$createCmd = "kafka-topics --create --topic $Topic --bootstrap-server $Bootstrap --partitions $Partitions --replication-factor $Replication"
$describeCmd = "kafka-topics --describe --topic $Topic --bootstrap-server $Bootstrap"

function Use-HostOrContainer {
    param([string]$command)

    if (Get-Command kafka-topics -ErrorAction SilentlyContinue) {
        Write-Host "Using host Kafka CLI"
        Invoke-Expression $command
    }
    else {
        Write-Host "Host CLI not found. Trying Docker container '$ContainerName'..."

        if (-not (docker ps | Select-String $ContainerName)) {
            Write-Error "Kafka container '$ContainerName' is not running."
            exit 1
        }

        docker exec -i $ContainerName sh -c $command
    }
}

Write-Host "`nChecking if topic '$Topic' exists..."
try {
    Use-HostOrContainer $describeCmd | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Topic '$Topic' already exists. Skipping creation."
        exit 0
    }
}
catch {}

Write-Host "Creating Kafka topic: $Topic"
Use-HostOrContainer $createCmd

Write-Host "`nVerifying topic creation..."
Use-HostOrContainer $describeCmd
Write-Host "Topic '$Topic' created successfully!"
