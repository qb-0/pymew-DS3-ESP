import pymew as pm

from . import offsets as off


class TArray(pm.mem.Struct):
    data = pm.mem.ptr.at(0x00)
    count = pm.mem.i32.at(0x08)


class UStructInfo(pm.mem.Struct):
    name_index = pm.mem.u32.at(off.UOBJECT_NAME)
    super = pm.mem.ptr.at(off.USTRUCT_SUPER)
    size = pm.mem.u32.at(off.USTRUCT_SIZE)


class UWorld(pm.mem.Struct):
    persistent_level = pm.mem.ptr.at(off.UWORLD_PERSISTENT_LEVEL)
    levels = TArray.at(off.UWORLD_LEVELS)
    owning_game_instance = pm.mem.ptr.at(off.UWORLD_OWNING_GAME_INSTANCE)


class UGameInstance(pm.mem.Struct):
    local_players = TArray.at(off.UGAMEINSTANCE_LOCAL_PLAYERS)


class ULocalPlayer(pm.mem.Struct):
    player_controller = pm.mem.ptr.at(off.ULOCALPLAYER_PLAYER_CONTROLLER)


class APlayerController(pm.mem.Struct):
    pawn = pm.mem.ptr.at(off.ACONTROLLER_PAWN)
    acknowledged_pawn = pm.mem.ptr.at(off.APLAYERCONTROLLER_ACKNOWLEDGED_PAWN)
    camera_manager = pm.mem.ptr.at(off.APLAYERCONTROLLER_CAMERA_MANAGER)


class ULevel(pm.mem.Struct):
    actors = TArray.at(off.ULEVEL_ACTORS)


class CameraPOV(pm.mem.Struct):
    location = pm.mem.vec3.at(off.POV_LOCATION)
    rotation = pm.mem.vec3.at(off.POV_ROTATION)
    fov = pm.mem.f32.at(off.POV_FOV)


class ActorSnapshot(pm.mem.Struct):
    class_ = pm.mem.ptr.at(off.UOBJECT_CLASS)
    root_component = pm.mem.ptr.at(off.ACTOR_ROOT_COMPONENT)


class CharacterSnapshot(pm.mem.Struct):
    class_ = pm.mem.ptr.at(off.UOBJECT_CLASS)
    root_component = pm.mem.ptr.at(off.ACTOR_ROOT_COMPONENT)
    capsule = pm.mem.ptr.at(off.ACHARACTER_CAPSULE_COMPONENT)
    faction = pm.mem.ptr.at(off.CHARGUNFIRE_FACTION)
    health = pm.mem.f32.at(off.CHARGUNFIRE_HEALTH)


class HumanSnapshot(pm.mem.Struct):
    fade_detector = pm.mem.ptr.at(off.HUMAN_FADE_DETECTOR)


class CapsuleDims(pm.mem.Struct):
    half_height = pm.mem.f32.at(off.CAPSULE_HALF_HEIGHT)
    radius = pm.mem.f32.at(off.CAPSULE_RADIUS)


class FactionAffiliation(pm.mem.Struct):
    faction1 = pm.mem.ptr.at(0x00)
    faction2 = pm.mem.ptr.at(0x08)
    affiliation = pm.mem.u8.at(0x10)


class FactionSettings(pm.mem.Struct):
    affiliations = TArray.at(off.UFACTIONSETTINGS_AFFILIATIONS)
