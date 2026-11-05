import os

src_path = r"D:\Modding\MarioPhysics\src\dll_main.cpp"
with open(src_path, "r", encoding="utf-8") as f:
    text = f.read()

target = """        // Wait until the map finishes streaming in (non-zero position)
        if (!worldInitialized && (std::abs(erPos.x) + std::abs(erPos.y) + std::abs(erPos.z) > 1.0f)) {
            origin = erPos;
            currentErPos = erPos;
            lastSafeGroundY = erPos.y;
            sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_health(marioId, 0x0880);
            worldInitialized = true;
            LogMsg("[WORLD] Jogador entrou no mundo em (%.2f, %.2f, %.2f)! Origin fixada.", erPos.x, erPos.y, erPos.z);
        }"""

replacement = """        // Menus / Character Selection / Loading Screen: player is at dummy coordinates (0, 0, 1.04)
        bool inWorldCoords = (std::abs(erPos.x) > 5.0f || std::abs(erPos.z) > 5.0f || erPos.y > 10.0f);
        if (!inWorldCoords) {
            worldInitialized = false;
            Sleep(8);
            continue;
        }

        // Initialize Mario once real world coordinates are loaded
        if (!worldInitialized) {
            origin = erPos;
            currentErPos = erPos;
            lastSafeGroundY = erPos.y;
            sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_health(marioId, 0x0880);
            worldInitialized = true;
            LogMsg("[WORLD] Jogador entrou no mundo em (%.2f, %.2f, %.2f)! Origin fixada.", erPos.x, erPos.y, erPos.z);
        }"""

assert target in text, "target not found in dll_main.cpp"
text = text.replace(target, replacement, 1)

with open(src_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Successfully applied loading screen guard to dll_main.cpp!")
