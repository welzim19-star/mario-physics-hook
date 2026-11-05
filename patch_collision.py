import os

src_path = r"D:\Modding\MarioPhysics\src\dll_main.cpp"
with open(src_path, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Add HavokPosition and CastRayER
cast_ray_code = """// --- Havok Raycasting for Wall and Ground Collision ---
struct HavokPosition {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
    float w = 0.0f;
};

static bool CastRayER(uintptr_t exeBase, uintptr_t playerIns, const Vec3& from, const Vec3& delta, Vec3& hitPos, uint32_t filter = 0x08) {
    if (!exeBase) return false;

    // CSHavokMan singleton at exeBase + 0x3d76068
    uintptr_t havokManPtr = *(uintptr_t*)(exeBase + 0x3d76068);
    if (!havokManPtr) {
        typedef void* (*FnGetHavokMan)();
        FnGetHavokMan getHavokMan = (FnGetHavokMan)(exeBase + 0xc4ff50);
        havokManPtr = (uintptr_t)getHavokMan();
    }
    if (!IsValidPtr(havokManPtr, 0xa0)) return false;

    void* physWorld = *(void**)(havokManPtr + 0x98);
    if (!physWorld || !IsValidPtr((uintptr_t)physWorld, 0x10)) return false;

    HavokPosition start = {from.x, from.y, from.z, 0.0f};
    HavokPosition ext   = {delta.x, delta.y, delta.z, 0.0f};
    HavokPosition outHit = {};

    typedef bool (*FnCastRay)(void* physWorld, uint32_t filter, const HavokPosition* start, const HavokPosition* delta, HavokPosition* outHit, void* owner);
    FnCastRay castRay = (FnCastRay)(exeBase + 0xc70090);

    bool hit = castRay(physWorld, filter, &start, &ext, &outHit, (void*)playerIns);
    if (hit) {
        hitPos = {outHit.x, outHit.y, outHit.z};
        return true;
    }
    return false;
}

// --- Main Thread ---"""

marker1 = "// --- Main Thread ---"
assert marker1 in text, "marker1 not found"
text = text.replace(marker1, cast_ray_code, 1)

# 2. Replace variables in MainLoopThread
old_vars = """    PoseSet prevPose = initRel;
    PoseSet currPose = initRel;
    Vec3 origin = {0.0f, 0.0f, 0.0f};
    Vec3 lastErPos = {0.0f, 0.0f, 0.0f};
    bool worldInitialized = false;
    uintptr_t loggedPlayerIns = 0;"""

new_vars = """    PoseSet prevPose = initRel;
    PoseSet currPose = initRel;
    Vec3 origin = {0.0f, 0.0f, 0.0f};
    Vec3 currentErPos = {0.0f, 0.0f, 0.0f};
    float lastSafeGroundY = 0.0f;
    bool worldInitialized = false;
    uintptr_t loggedPlayerIns = 0;"""

assert old_vars in text, "old_vars not found"
text = text.replace(old_vars, new_vars, 1)

# 3. Replace worldInitialized & teleport logic
old_teleport = """        // Wait until the map finishes streaming in (non-zero position)
        if (!worldInitialized && (std::abs(erPos.x) + std::abs(erPos.y) + std::abs(erPos.z) > 1.0f)) {
            origin = erPos;
            lastErPos = erPos;
            sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_health(marioId, 0x0880);
            worldInitialized = true;
            LogMsg("[WORLD] Jogador entrou no mundo em (%.2f, %.2f, %.2f)! Origin fixada.", erPos.x, erPos.y, erPos.z);
        }

        // Detect fast travel / teleports: re-center origin smoothly
        if (worldInitialized) {
            float warpDist = erPos.dist(lastErPos);
            if (warpDist > 8.0f) {
                origin = erPos;
                sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
                sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
                state.position[0] = 0.0f;
                state.position[1] = 0.0f;
                state.position[2] = 0.0f;
                LogMsg("[WORLD] Teleporte detectado (dist=%.2f m)! Re-centrado.", warpDist);
            }
        }
        lastErPos = erPos;"""

new_teleport = """        // Wait until the map finishes streaming in (non-zero position)
        if (!worldInitialized && (std::abs(erPos.x) + std::abs(erPos.y) + std::abs(erPos.z) > 1.0f)) {
            origin = erPos;
            currentErPos = erPos;
            lastSafeGroundY = erPos.y;
            sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_health(marioId, 0x0880);
            worldInitialized = true;
            LogMsg("[WORLD] Jogador entrou no mundo em (%.2f, %.2f, %.2f)! Origin fixada.", erPos.x, erPos.y, erPos.z);
        }

        // Detect fast travel / teleports: re-center origin smoothly
        if (worldInitialized) {
            float warpDist = erPos.dist(currentErPos);
            if (warpDist > 45.0f) {
                origin = erPos;
                currentErPos = erPos;
                lastSafeGroundY = erPos.y;
                sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
                sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
                state.position[0] = 0.0f;
                state.position[1] = 0.0f;
                state.position[2] = 0.0f;
                LogMsg("[WORLD] Teleporte detectado (dist=%.2f m)! Re-centrado.", warpDist);
            }
        }"""

assert old_teleport in text, "old_teleport not found"
text = text.replace(old_teleport, new_teleport, 1)

# 4. Replace movement application in tick loop
old_movement = """            // Calculate target world position from SM64
            Vec3 targetErPos;
            targetErPos.x = origin.x - state.position[0] * SCALE_ER; // mirrored on X
            targetErPos.y = origin.y + state.position[1] * SCALE_ER; // Y is up
            targetErPos.z = origin.z + state.position[2] * SCALE_ER; // Z is forward

            bool nowAirborne = (state.action & 0x00000800) != 0;

            if (nowAirborne) {
                // Airborne (Jumping / Long Jump / Dive / Ground Pound):
                // Disable Elden Ring gravity so it does not pull Mario down early!
                *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true
                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x74) = targetErPos.y;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true
            } else {
                // Grounded: Enable Souls gravity so capsule rests on the terrain
                *(uint8_t*)(physMod + 0x1d5) = 0; // gravity_disabled = false
                *(uint8_t*)(physMod + 0x1d0) = 0; // is_falling = false
                *(uint8_t*)(physMod + 0x1d1) = 1; // is_touching_ground = true
                *(uint8_t*)(physMod + 0x92) = 1;  // standing_on_solid_ground = true
                *(uint8_t*)(physMod + 0x93) = 1;  // touching_solid_ground = true

                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true

                // Keep origin.y synchronized with actual ground height
                float realGroundY = *(float*)(physMod + 0x74);
                origin.y = realGroundY - state.position[1] * SCALE_ER;
            }

            // Character rotation follows Mario's face angle
            Quat q = Quat::from_rotation_y(PI_F - state.faceAngle);
            *(float*)(physMod + 0x50) = q.x;
            *(float*)(physMod + 0x54) = q.y;
            *(float*)(physMod + 0x58) = q.z;
            *(float*)(physMod + 0x5C) = q.w;

            // Re-centre SM64 coordinate space when traveling beyond 25m
            if (std::abs(state.position[0]) > 2500.0f || std::abs(state.position[2]) > 2500.0f) {
                origin = targetErPos;
                sm64_set_mario_position(marioId, 0.0f, state.position[1], 0.0f);
                state.position[0] = 0.0f;
                state.position[2] = 0.0f;
            }"""

new_movement = """            // Calculate target world position from SM64
            Vec3 targetErPos;
            targetErPos.x = origin.x - state.position[0] * SCALE_ER; // mirrored on X
            targetErPos.y = origin.y + state.position[1] * SCALE_ER; // Y is up
            targetErPos.z = origin.z + state.position[2] * SCALE_ER; // Z is forward

            // --- 1. WALL COLLISION & SLIDE (RAYCAST SWEEP) ---
            constexpr float PLAYER_RADIUS = 0.35f;
            Vec3 moveDelta = targetErPos - currentErPos;
            float horizMove = std::sqrt(moveDelta.x * moveDelta.x + moveDelta.z * moveDelta.z);

            Vec3 finalTarget = targetErPos;
            bool hitWallX = false;
            bool hitWallZ = false;

            if (horizMove > 0.0005f) {
                // Test at knee (0.4m) and chest (1.1m)
                float rayHeights[2] = {currentErPos.y + 0.40f, currentErPos.y + 1.10f};

                // Test X axis movement
                if (std::abs(moveDelta.x) > 0.0002f) {
                    float signX = (moveDelta.x > 0.0f) ? 1.0f : -1.0f;
                    float probeDistX = std::abs(moveDelta.x) + PLAYER_RADIUS;
                    Vec3 rayDeltaX = {signX * probeDistX, 0.0f, 0.0f};

                    for (float h : rayHeights) {
                        Vec3 hitPoint;
                        Vec3 rayStart = {currentErPos.x, h, currentErPos.z};
                        if (CastRayER(exeBase, playerIns, rayStart, rayDeltaX, hitPoint, 0x08)) {
                            float distToHit = std::abs(hitPoint.x - currentErPos.x);
                            if (distToHit <= probeDistX) {
                                hitWallX = true;
                                float allowedX = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                finalTarget.x = currentErPos.x + signX * allowedX;
                                break;
                            }
                        }
                    }
                }

                // Test Z axis movement
                if (std::abs(moveDelta.z) > 0.0002f) {
                    float signZ = (moveDelta.z > 0.0f) ? 1.0f : -1.0f;
                    float probeDistZ = std::abs(moveDelta.z) + PLAYER_RADIUS;
                    Vec3 rayDeltaZ = {0.0f, 0.0f, signZ * probeDistZ};

                    for (float h : rayHeights) {
                        Vec3 hitPoint;
                        Vec3 rayStart = {finalTarget.x, h, currentErPos.z};
                        if (CastRayER(exeBase, playerIns, rayStart, rayDeltaZ, hitPoint, 0x08)) {
                            float distToHit = std::abs(hitPoint.z - currentErPos.z);
                            if (distToHit <= probeDistZ) {
                                hitWallZ = true;
                                float allowedZ = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                finalTarget.z = currentErPos.z + signZ * allowedZ;
                                break;
                            }
                        }
                    }
                }

                if (hitWallX || hitWallZ) {
                    targetErPos.x = finalTarget.x;
                    targetErPos.z = finalTarget.z;

                    // Sync clamped coordinates back to libsm64 so Mario does not penetrate walls
                    float sm64_x = -(targetErPos.x - origin.x) / SCALE_ER;
                    float sm64_z =  (targetErPos.z - origin.z) / SCALE_ER;
                    sm64_set_mario_position(marioId, sm64_x, state.position[1], sm64_z);
                    state.position[0] = sm64_x;
                    state.position[2] = sm64_z;

                    // Stop forward momentum if both axes are blocked (hitting a wall head-on)
                    if (hitWallX && hitWallZ) {
                        sm64_set_mario_velocity(marioId, 0.0f, state.velocity[1], 0.0f);
                    }
                }
            }

            // --- 2. GROUND & ABYSS DETECTION ---
            bool nowAirborne = (state.action & 0x00000800) != 0;

            // Probe ground directly under Mario (from current knee height down 4.5m)
            Vec3 groundStart = {targetErPos.x, currentErPos.y + 0.60f, targetErPos.z};
            Vec3 groundDelta = {0.0f, -4.50f, 0.0f};
            Vec3 groundHit;
            bool groundFound = CastRayER(exeBase, playerIns, groundStart, groundDelta, groundHit, 0x08);

            if (groundFound) {
                lastSafeGroundY = groundHit.y;
            }

            if (nowAirborne) {
                // Airborne (Jumping / Long Jump / Dive / Ground Pound):
                // Disable Elden Ring gravity so Havok does not drag Mario down prematurely
                *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true

                // Check landing: if Mario has descended to or below the ground surface
                if (groundFound && targetErPos.y <= groundHit.y + 0.05f) {
                    targetErPos.y = groundHit.y;
                    origin.y = groundHit.y - state.position[1] * SCALE_ER;
                }

                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x74) = targetErPos.y;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true
            } else {
                // Grounded:
                if (groundFound) {
                    float dy = groundHit.y - currentErPos.y;
                    if (dy < 1.0f) { // Smooth step up / down stairs and ramps
                        targetErPos.y = groundHit.y;
                        origin.y = groundHit.y - state.position[1] * SCALE_ER;
                    }
                } else {
                    // Stepping over cliff or void: lock origin to last safe ground
                    // so Mario falls naturally instead of snapping into the abyss
                    targetErPos.y = lastSafeGroundY + state.position[1] * SCALE_ER;
                    origin.y = lastSafeGroundY - state.position[1] * SCALE_ER;
                }

                *(uint8_t*)(physMod + 0x1d5) = 0; // gravity_disabled = false
                *(uint8_t*)(physMod + 0x1d0) = 0; // is_falling = false
                *(uint8_t*)(physMod + 0x1d1) = 1; // is_touching_ground = true
                *(uint8_t*)(physMod + 0x92) = 1;  // standing_on_solid_ground = true
                *(uint8_t*)(physMod + 0x93) = 1;  // touching_solid_ground = true

                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x74) = targetErPos.y;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true
            }

            currentErPos = targetErPos;

            // Character rotation follows Mario's face angle
            Quat q = Quat::from_rotation_y(PI_F - state.faceAngle);
            *(float*)(physMod + 0x50) = q.x;
            *(float*)(physMod + 0x54) = q.y;
            *(float*)(physMod + 0x58) = q.z;
            *(float*)(physMod + 0x5C) = q.w;

            // Re-centre SM64 coordinate space when traveling beyond 25m
            if (std::abs(state.position[0]) > 2500.0f || std::abs(state.position[2]) > 2500.0f) {
                origin = targetErPos;
                currentErPos = targetErPos;
                sm64_set_mario_position(marioId, 0.0f, state.position[1], 0.0f);
                state.position[0] = 0.0f;
                state.position[2] = 0.0f;
            }"""

assert old_movement in text, "old_movement not found"
text = text.replace(old_movement, new_movement, 1)

with open(src_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Successfully applied collision fix to dll_main.cpp!")
