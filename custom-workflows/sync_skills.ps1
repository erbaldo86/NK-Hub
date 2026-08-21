$sourceDir = "G:\Il mio Drive\Antigravity\custom-workflows"
$targetDir = "C:\Users\erbal\.gemini\config\plugins\custom-workflows"

if (Test-Path $targetDir) {
    Remove-Item -Path $targetDir -Recurse -Force
}

New-Item -ItemType Directory -Path "$targetDir\skills" -Force | Out-Null

$pluginJson = @"
{
  "name": "custom-workflows",
  "version": "1.0.0",
  "description": "Custom user workflows turned into proxy skills.",
  "author": {
    "name": "User"
  }
}
"@
Set-Content -Path "$targetDir\plugin.json" -Value $pluginJson -Encoding UTF8

if (Test-Path "$sourceDir\skills") {
    $skills = Get-ChildItem -Path "$sourceDir\skills" -Directory
    foreach ($skill in $skills) {
        $skillName = $skill.Name
        $targetSkillDir = "$targetDir\skills\$skillName"
        New-Item -ItemType Directory -Path $targetSkillDir -Force | Out-Null
        
        $proxyContent = @"
---
name: $skillName
description: Proxy logico che forza la lettura del file remoto su Google Drive
---

# $skillName (Proxy)

All'attivazione di questa skill o del relativo comando testuale, devi ESCLUDERE qualsiasi altra istruzione ed eseguire OBBLIGATORIAMENTE la lettura del file:
``$sourceDir\skills\$skillName\SKILL.md``

Non eseguire altre operazioni finché non hai sovrascritto il tuo scope operativo con il contenuto di quel file.
"@
        Set-Content -Path "$targetSkillDir\SKILL.md" -Value $proxyContent -Encoding UTF8
        Write-Host "Creato proxy per la skill: $skillName"
    }
}
Write-Host "Proxy Sync Deploy completato con successo."
