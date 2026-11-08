<div align="right">
  <a href="README.md">English</a> | <strong>Português</strong>
</div>

# Mario Physics Hook (Motor de Modding Nativo C++ para Elden Ring) 🎮🔧

[![Linguagem](https://img.shields.io/badge/Linguagem-C%2B%2B20%20%2F%20C-blue.svg)]()
[![Alvo](https://img.shields.io/badge/Processo-x86__64%20PE%20Nativo-purple.svg)]()
[![Hook](https://img.shields.io/badge/Hook-Biblioteca%20MinHook-red.svg)](https://github.com/TsudaKageyu/minhook)
[![Física](https://img.shields.io/badge/Motor-libsm64%20Nativa-brightgreen.svg)](https://github.com/libsm64/libsm64)
[![Licença](https://img.shields.io/badge/Licen%C3%A7a-MIT-orange.svg)](LICENSE)

> **Hook Nativo de Memória e Ponte de Física em C++ para Elden Ring.**  
> Intercepta a memória do processo e as rotinas de tick de física do jogo via detours x86_64, embutindo o motor de física autêntico do Super Mario 64 (`libsm64`) diretamente no runtime do executável AAA.

---

## 📌 Fluxo Arquitetural (Hooking de Memória & Detours)

A DLL intercepta o loop do jogo por trampolins com MinHook, processa os ticks da física do SM64 e projeta as transformações calculadas diretamente na memória do controlador de personagens Havok do Elden Ring.

```mermaid
flowchart TD
    subgraph PROCESS["eldenring.exe (Processo Alvo)"]
        Havok["Loop de Física Havok"]
        Render["Pipeline de Matrizes Render"]
    end

    subgraph INJECTED_DLL["mario_physics.dll (Hook)"]
        MinHook["Trampolim MinHook"]
        Bridge["Controlador de Física SM64"]
        SM64["Biblioteca Estática libsm64"]
        
        MinHook <--> Havok
        MinHook --> Bridge
        Bridge <--> SM64
        Bridge --> Render
    end

    subgraph SCRIPTS["Pipeline de Diagnóstico"]
        PyCapture["Inspetor de Memória Python"]
        PyFreezeFix["Fixador de Travamentos"]
    end

    SCRIPTS -.-> PROCESS
```

---

## ⚙️ Conquistas Centrais de Engenharia

### 1. Detours em Memória sem Travamentos via MinHook
- Intercepta as rotinas de cinemática do jogador sem corromper as threads paralelas da engine Havok nem acionar proteções de pilha do compilador.
- Restaura a execução original do código de máquina através de trampolins limpos no encerramento.

### 2. Sincronização de Frequência de Ticks Diferentes
- Resolve a divergência entre a simulação de 30Hz do SM64 e o clock de física de 60Hz do Elden Ring utilizando interpolação linear e filas acumuladoras de velocidade.

### 3. Injeção Dinâmica de Superfícies de Colisão
- Lê as árvores de geometria estática da engine e injeta os triângulos como superfícies de colisão dinâmicas na memória do SM64 em tempo real.

---

## 🛠️ Compilação

### Requisitos
- Ferramentas de compilação C++ MSVC v143 ou superior (Visual Studio 2022)
- Windows SDK 10.0+ (x86_64)

```bash
# Compilar a DLL nativa
build.bat
# Saída: bin/mario_physics.dll
```

---

## ⚖️ Aviso Legal & Uso Educacional
*Este projeto é uma ferramenta educacional independente de engenharia reversa e modding em ambiente limpo (*clean-room*). Não distribui nem contém arquivos proprietários da FromSoftware, modelos protegidos ou ROMs de jogos.*
