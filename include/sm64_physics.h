#pragma once

#include "sm64_types.h"

namespace SM64 {

void InitMario(MarioState* m);
void SetAction(MarioState* m, u32 action);

// Atualiza o estado das entradas do teclado/mouse mapeadas
void ProcessInputs(
    MarioState* m,
    bool keyW, bool keyA, bool keyS, bool keyD,
    bool spacePressed, bool spaceDown,
    bool rmbDown,
    bool lmbPressed,
    bool keyEPressed,
    float mouseDeltaX,
    float cameraYaw
);

// Executa um tick de simulação da física (60Hz / delta_time)
void Step(MarioState* m, float dt);
void NotifyLanded(MarioState* m, float newFloorY);

// Converte graus/radianos para a representação s16 do SM64 (0..65535)
inline s16 RadToS16(float rad) {
    return static_cast<s16>(rad * (32768.0f / 3.14159265358979323846f));
}

inline float S16ToRad(s16 angle) {
    return static_cast<float>(angle) * (3.14159265358979323846f / 32768.0f);
}

} // namespace SM64
