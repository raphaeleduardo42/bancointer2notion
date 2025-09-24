<#
.SYNOPSIS
    Executa o script de sincronização de transações do Banco Inter para o Notion.

.DESCRIPTION
    Este script automatiza todo o processo de execução do projeto. Ele garante que o ambiente
    virtual ('venv') exista e esteja configurado corretamente antes de executar o script principal 'main.py'.

    As etapas executadas são:
    1. Verifica a existência do arquivo 'requirements.txt'. Se não existir, exibe um erro.
    2. Verifica se o ambiente virtual ('venv') existe.
    3. Se o ambiente não existir, ele é criado e as dependências do 'requirements.txt' são instaladas.
    4. Ativa o ambiente virtual.
    5. Executa o script 'main.py'.

.EXAMPLE
    .\run.ps1
    Executa o script a partir do diretório raiz do projeto.
#>
# Ativa o modo estrito para garantir a qualidade do código e para o script em caso de erros.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Obtém o diretório onde o script está localizado.
$ScriptDir = $PSScriptRoot

# Define os caminhos para os arquivos e diretórios necessários.
$VenvDir = Join-Path $ScriptDir ".venv"
$VenvActivate = Join-Path $VenvDir "Scripts\Activate.ps1"
$MainScript = Join-Path $ScriptDir "main.py"
$RequirementsFile = Join-Path $ScriptDir "requirements.txt"

# Verifica se o arquivo de dependências existe. Se não, o projeto está incompleto.
if (-not (Test-Path $RequirementsFile)) {
    Write-Error "❌ Arquivo 'requirements.txt' não encontrado. Por favor, execute 'git pull' para garantir que todos os arquivos do projeto estão atualizados."
    # O script para aqui por causa de $ErrorActionPreference = "Stop"
}

# Verifica se o ambiente virtual existe. Se não, cria e instala as dependências.
if (-not (Test-Path $VenvDir)) {
    Write-Host "⚠️  Ambiente virtual não encontrado. Criando um novo em '$VenvDir'..."
    
    # Cria o ambiente virtual usando o módulo venv do Python.
    python -m venv $VenvDir
    Write-Host "✅ Ambiente virtual criado com sucesso."

    # Ativa o ambiente virtual na sessão atual para poder usar o pip dele.
    . $VenvActivate

    # Instala as dependências. Já verificamos que o arquivo existe.
    Write-Host "📦 Instalando dependências de '$RequirementsFile'..."
    pip install -r $RequirementsFile
    Write-Host "✅ Dependências instaladas."
}

try {
    # Ativa o ambiente virtual no escopo atual usando o operador de ponto (.).
    . $VenvActivate
    Write-Host "✅ Ambiente virtual ativado e pronto."
    
    Write-Host "▶️  Iniciando a sincronização..."
    # Executa o script Python.
    python $MainScript

    # Verifica se o script Python foi executado com sucesso (código de saída 0).
    if ($LASTEXITCODE -ne 0) {
        # Lança um erro para ser capturado pelo bloco catch.
        throw "O script Python terminou com um erro (código de saída: $LASTEXITCODE)."
    }

    Write-Host "🎉 Sincronização concluída com sucesso!"

} catch {
    Write-Error "❌ A sincronização falhou. Verifique os logs de erro acima."
} finally {
    Write-Host "🏁 Script de execução finalizado."
}
