with open(r"D:\Modding\MarioPhysics\src\dll_main.cpp", "rb") as f:
    content = f.read().decode("utf-8")

old_cast_ray = """static bool CastRayER(uintptr_t exeBase, uintptr_t playerIns, const Vec3& from, const Vec3& delta, Vec3& hitPos, uint32_t filter = 0x2000058) {
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
    FnCastRay castRay = (FnCastRay)(exeBase + 0xc70090); // Verified RVA for cs_phys_world_cast_ray in Elden Ring

    bool hit = castRay(physWorld, filter, &start, &ext, &outHit, (void*)playerIns);
    if (hit) {
        hitPos = {outHit.x, outHit.y, outHit.z};
        return true;
    }
    return false;
}"""

new_cast_ray = """static bool CastRayER(uintptr_t exeBase, uintptr_t playerIns, const Vec3& from, const Vec3& delta, Vec3& hitPos, uint32_t filter = 0x2000058) {
    if (!exeBase || !playerIns || !IsValidPtr(playerIns, 0x200)) return false;

    uintptr_t modBag = *(uintptr_t*)(playerIns + 0x190);
    if (!IsValidPtr(modBag, 0x80)) return false;

    uintptr_t physMod = *(uintptr_t*)(modBag + 0x68);
    if (!IsValidPtr(physMod, 0x100)) return false;

    uintptr_t chrProxy = *(uintptr_t*)(physMod + 0x98);
    if (!IsValidPtr(chrProxy, 0x20)) return false;

    void* physWorld = *(void**)(chrProxy + 0x18);
    if (!physWorld || !IsValidPtr((uintptr_t)physWorld, 0x10)) return false;

    if (*(uintptr_t*)((uintptr_t)physWorld + 8) == 0) return false;

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

static bool CastWallRay(uintptr_t exeBase, uintptr_t playerIns, const Vec3& from, const Vec3& delta, Vec3& hitPoint) {
    if (CastRayER(exeBase, playerIns, from, delta, hitPoint, 0x2000058)) return true;
    return CastRayER(exeBase, playerIns, from, delta, hitPoint, 0x08);
}"""

# Normalize CRLF
content_norm = content.replace("\r\n", "\n")
old_cast_ray_norm = old_cast_ray.replace("\r\n", "\n")
assert old_cast_ray_norm in content_norm, "old_cast_ray not found!"
content_norm = content_norm.replace(old_cast_ray_norm, new_cast_ray.replace("\r\n", "\n"), 1)

# Now update the collision loops to use CastWallRay and bulletproof ground detection
old_collision_part = """                // A. Direct Forward Sweep along moveDelta (blocks doors and angled walls)
                Vec3 fwdDir = {moveDelta.x / horizMove, 0.0f, moveDelta.z / horizMove};
                float probeDistFwd = horizMove + PLAYER_RADIUS;
                Vec3 rayDeltaFwd = {fwdDir.x * probeDistFwd, 0.0f, fwdDir.z * probeDistFwd};

                for (float h : rayHeights) {
                    Vec3 hitPoint;
                    Vec3 rayStart = {currentErPos.x, h, currentErPos.z};
                    if (CastRayER(exeBase, playerIns, rayStart, rayDeltaFwd, hitPoint, COL_FILTER)) {
                        float distToHit = std::sqrt((hitPoint.x - currentErPos.x)*(hitPoint.x - currentErPos.x) + 
                                                    (hitPoint.z - currentErPos.z)*(hitPoint.z - currentErPos.z));
                        if (distToHit <= probeDistFwd) {
                            hitWall = true;
                            float allowed = std::max(0.0f, distToHit - PLAYER_RADIUS);
                            finalTarget.x = currentErPos.x + fwdDir.x * allowed;
                            finalTarget.z = currentErPos.z + fwdDir.z * allowed;
                            break;
                        }
                    }
                }

                // B. Separate X and Z sweeps for smooth sliding along wall and door surfaces
                if (!hitWall) {
                    if (std::abs(moveDelta.x) > 0.0002f) {
                        float signX = (moveDelta.x > 0.0f) ? 1.0f : -1.0f;
                        float probeDistX = std::abs(moveDelta.x) + PLAYER_RADIUS;
                        Vec3 rayDeltaX = {signX * probeDistX, 0.0f, 0.0f};

                        for (float h : rayHeights) {
                            Vec3 hitPoint;
                            Vec3 rayStart = {currentErPos.x, h, currentErPos.z};
                            if (CastRayER(exeBase, playerIns, rayStart, rayDeltaX, hitPoint, COL_FILTER)) {
                                float distToHit = std::abs(hitPoint.x - currentErPos.x);
                                if (distToHit <= probeDistX) {
                                    hitWall = true;
                                    float allowedX = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                    finalTarget.x = currentErPos.x + signX * allowedX;
                                    break;
                                }
                            }
                        }
                    }

                    if (std::abs(moveDelta.z) > 0.0002f) {
                        float signZ = (moveDelta.z > 0.0f) ? 1.0f : -1.0f;
                        float probeDistZ = std::abs(moveDelta.z) + PLAYER_RADIUS;
                        Vec3 rayDeltaZ = {0.0f, 0.0f, signZ * probeDistZ};

                        for (float h : rayHeights) {
                            Vec3 hitPoint;
                            Vec3 rayStart = {finalTarget.x, h, currentErPos.z};
                            if (CastRayER(exeBase, playerIns, rayStart, rayDeltaZ, hitPoint, COL_FILTER)) {
                                float distToHit = std::abs(hitPoint.z - currentErPos.z);
                                if (distToHit <= probeDistZ) {
                                    hitWall = true;
                                    float allowedZ = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                    finalTarget.z = currentErPos.z + signZ * allowedZ;
                                    break;
                                }
                            }
                        }
                    }
                }"""

new_collision_part = """                // A. Direct Forward Sweep along moveDelta (blocks doors and angled walls)
                Vec3 fwdDir = {moveDelta.x / horizMove, 0.0f, moveDelta.z / horizMove};
                float probeDistFwd = horizMove + PLAYER_RADIUS;
                Vec3 rayDeltaFwd = {fwdDir.x * probeDistFwd, 0.0f, fwdDir.z * probeDistFwd};

                for (float h : rayHeights) {
                    Vec3 hitPoint;
                    Vec3 rayStart = {currentErPos.x, h, currentErPos.z};
                    if (CastWallRay(exeBase, playerIns, rayStart, rayDeltaFwd, hitPoint)) {
                        float distToHit = std::sqrt((hitPoint.x - currentErPos.x)*(hitPoint.x - currentErPos.x) + 
                                                    (hitPoint.z - currentErPos.z)*(hitPoint.z - currentErPos.z));
                        if (distToHit <= probeDistFwd) {
                            hitWall = true;
                            float allowed = std::max(0.0f, distToHit - PLAYER_RADIUS);
                            finalTarget.x = currentErPos.x + fwdDir.x * allowed;
                            finalTarget.z = currentErPos.z + fwdDir.z * allowed;
                            break;
                        }
                    }
                }

                // B. Separate X and Z sweeps for smooth sliding along wall and door surfaces
                if (!hitWall) {
                    if (std::abs(moveDelta.x) > 0.0002f) {
                        float signX = (moveDelta.x > 0.0f) ? 1.0f : -1.0f;
                        float probeDistX = std::abs(moveDelta.x) + PLAYER_RADIUS;
                        Vec3 rayDeltaX = {signX * probeDistX, 0.0f, 0.0f};

                        for (float h : rayHeights) {
                            Vec3 hitPoint;
                            Vec3 rayStart = {currentErPos.x, h, currentErPos.z};
                            if (CastWallRay(exeBase, playerIns, rayStart, rayDeltaX, hitPoint)) {
                                float distToHit = std::abs(hitPoint.x - currentErPos.x);
                                if (distToHit <= probeDistX) {
                                    hitWall = true;
                                    float allowedX = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                    finalTarget.x = currentErPos.x + signX * allowedX;
                                    break;
                                }
                            }
                        }
                    }

                    if (std::abs(moveDelta.z) > 0.0002f) {
                        float signZ = (moveDelta.z > 0.0f) ? 1.0f : -1.0f;
                        float probeDistZ = std::abs(moveDelta.z) + PLAYER_RADIUS;
                        Vec3 rayDeltaZ = {0.0f, 0.0f, signZ * probeDistZ};

                        for (float h : rayHeights) {
                            Vec3 hitPoint;
                            Vec3 rayStart = {finalTarget.x, h, currentErPos.z};
                            if (CastWallRay(exeBase, playerIns, rayStart, rayDeltaZ, hitPoint)) {
                                float distToHit = std::abs(hitPoint.z - currentErPos.z);
                                if (distToHit <= probeDistZ) {
                                    hitWall = true;
                                    float allowedZ = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                    finalTarget.z = currentErPos.z + signZ * allowedZ;
                                    break;
                                }
                            }
                        }
                    }
                }"""

old_collision_part_norm = old_collision_part.replace("\r\n", "\n")
assert old_collision_part_norm in content_norm, "old_collision_part not found!"
content_norm = content_norm.replace(old_collision_part_norm, new_collision_part.replace("\r\n", "\n"), 1)

old_ceil_and_ground = """            // --- 2. CEILING COLLISION (PREVENTS POPPING THROUGH ROOFS/ATTICS) ---
            bool nowAirborne = (state.action & 0x00000800) != 0;
            if (nowAirborne && state.velocity[1] > 0.0f) {
                Vec3 ceilStart = {currentErPos.x, currentErPos.y + 1.00f, currentErPos.z};
                Vec3 ceilDelta = {0.0f, 1.80f, 0.0f};
                Vec3 ceilHit;
                if (CastRayER(exeBase, playerIns, ceilStart, ceilDelta, ceilHit, 0x2000058)) {
                    float maxAllowedY = ceilHit.y - 1.50f;
                    if (targetErPos.y > maxAllowedY) {
                        targetErPos.y = maxAllowedY;
                        // Bonk head on ceiling and fall back down!
                        sm64_set_mario_velocity(marioId, state.velocity[0], -6.0f, state.velocity[2]);
                    }
                }
            }

            // --- 3. ENVIRONMENT GROUND & LEDGE/CLIFF DETECTION ---
            Vec3 groundStart = {targetErPos.x, currentErPos.y + 0.60f, targetErPos.z};
            Vec3 groundDelta = {0.0f, -40.0f, 0.0f}; // Probe deep into world (40m)
            Vec3 groundHit;
            bool groundFound = CastRayER(exeBase, playerIns, groundStart, groundDelta, groundHit, 0x2000058);

            if (groundFound) {
                lastSafeGroundY = groundHit.y;
            }

            if (nowAirborne) {
                // Airborne (Jumping / Long Jump / Dive / Freefall / Ground Pound):
                *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true

                // Check landing: if Mario has descended to or below the real terrain surface
                if (groundFound && state.velocity[1] <= 0.0f && targetErPos.y <= groundHit.y + 0.08f) {
                    targetErPos.y = groundHit.y;
                    origin.y = groundHit.y;
                    sm64_set_mario_position(marioId, state.position[0], 0.0f, state.position[2]);
                    state.position[1] = 0.0f;
                }

                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x74) = targetErPos.y;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true
            } else {
                // Grounded:
                if (groundFound) {
                    float dropDist = currentErPos.y - groundHit.y;
                    if (dropDist > 0.60f) {
                        // Ground dropped significantly: Mario walked off a roof, cliff, or ledge!
                        // Trigger authentic SM64 freefall so he falls down naturally instead of walking in thin air
                        sm64_set_mario_action(marioId, 0x0100088C /* ACT_FREEFALL */);
                        origin.y = groundHit.y;
                        float smHeight = std::min(4000.0f, (currentErPos.y - groundHit.y) / SCALE_ER);
                        sm64_set_mario_position(marioId, state.position[0], smHeight, state.position[2]);
                        state.position[1] = smHeight;
                        *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true while falling
                    } else if (dropDist >= -0.80f) {
                        // Smooth step up or down stairs, ramps, and slopes
                        targetErPos.y = groundHit.y;
                        origin.y = groundHit.y;
                    }
                }"""

new_ceil_and_ground = """            // --- 2. CEILING COLLISION (PREVENTS POPPING THROUGH ROOFS/ATTICS) ---
            bool nowAirborne = (state.action & 0x00000800) != 0;
            if (nowAirborne && state.velocity[1] > 0.0f) {
                Vec3 ceilStart = {currentErPos.x, currentErPos.y + 0.80f, currentErPos.z};
                Vec3 ceilDelta = {0.0f, 2.00f, 0.0f};
                Vec3 ceilHit;
                if (CastWallRay(exeBase, playerIns, ceilStart, ceilDelta, ceilHit)) {
                    float maxAllowedY = ceilHit.y - 1.40f;
                    if (targetErPos.y > maxAllowedY) {
                        targetErPos.y = maxAllowedY;
                        // Bonk head on ceiling and fall back down!
                        sm64_set_mario_velocity(marioId, state.velocity[0], -6.0f, state.velocity[2]);
                    }
                }
            }

            // --- 3. ENVIRONMENT GROUND & LEDGE/CLIFF DETECTION ---
            Vec3 groundStart = {targetErPos.x, currentErPos.y + 1.20f, targetErPos.z};
            Vec3 groundDelta = {0.0f, -40.0f, 0.0f}; // Probe deep into world (40m)
            Vec3 groundHit;
            bool groundFound = CastRayER(exeBase, playerIns, groundStart, groundDelta, groundHit, 0x2000058);
            if (!groundFound) {
                groundFound = CastRayER(exeBase, playerIns, groundStart, groundDelta, groundHit, 0x08);
            }
            if (!groundFound && IsValidPtr(physMod, 0x2c0)) {
                float capY = *(float*)(physMod + 0x2a4);
                if (std::abs(capY - currentErPos.y) < 3.0f && capY > 1.0f) {
                    groundHit = {targetErPos.x, capY, targetErPos.z};
                    groundFound = true;
                }
            }

            if (groundFound) {
                lastSafeGroundY = groundHit.y;
            }

            if (nowAirborne) {
                // Airborne (Jumping / Long Jump / Dive / Freefall / Ground Pound):
                *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true

                // Check landing: if Mario has descended to or below the real terrain surface
                if (groundFound && state.velocity[1] <= 0.0f && targetErPos.y <= groundHit.y + 0.08f) {
                    targetErPos.y = groundHit.y;
                    origin.y = groundHit.y;
                    sm64_set_mario_position(marioId, state.position[0], 0.0f, state.position[2]);
                    state.position[1] = 0.0f;
                }

                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x74) = targetErPos.y;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true
            } else {
                // Grounded:
                if (groundFound) {
                    float dropDist = currentErPos.y - groundHit.y;
                    if (dropDist > 0.60f) {
                        // Ground dropped significantly: Mario walked off a roof, cliff, or ledge!
                        // Trigger authentic SM64 freefall so he falls down naturally instead of walking in thin air
                        sm64_set_mario_action(marioId, 0x0100088C /* ACT_FREEFALL */);
                        origin.y = groundHit.y;
                        float smHeight = std::min(4000.0f, (currentErPos.y - groundHit.y) / SCALE_ER);
                        sm64_set_mario_position(marioId, state.position[0], smHeight, state.position[2]);
                        state.position[1] = smHeight;
                        *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true while falling
                    } else if (dropDist >= -1.25f) {
                        // Smooth step up or down stairs, ramps, and slopes up to 1.25m
                        targetErPos.y = groundHit.y;
                        origin.y = groundHit.y;
                    }
                }"""

old_ceil_and_ground_norm = old_ceil_and_ground.replace("\r\n", "\n")
assert old_ceil_and_ground_norm in content_norm, "old_ceil_and_ground not found!"
content_norm = content_norm.replace(old_ceil_and_ground_norm, new_ceil_and_ground.replace("\r\n", "\n"), 1)

# Write back
with open(r"D:\Modding\MarioPhysics\src\dll_main.cpp", "wb") as f:
    f.write(content_norm.replace("\n", "\r\n").encode("utf-8"))

print("[SUCESSO] dll_main.cpp atualizado com sucesso!")
