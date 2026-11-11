"""Engine adapters. Each one reports real support limits. None returns a fake APK."""

from __future__ import annotations

from dataclasses import dataclass

from app.jobs.runner import probe_toolchain


@dataclass
class Adapter:
    engine_id: str
    native_export: bool
    notes: str

    def plan_command(self, version: str | None = None) -> str | None:
        return None

    def build_android(self, allow_execute: bool = False) -> dict:
        tools = probe_toolchain()
        missing = [tool["name"] for tool in tools if not tool["present"]]
        return {
            "engine": self.engine_id,
            "status": "failed",
            "code": "missing_toolchain" if missing else "execution_disabled",
            "executed": False,
            "command": self.plan_command(None),
            "missing": missing,
            "message": (
                self.notes
                if not missing
                else "Toolchain is incomplete. No package was generated."
            ),
        }


class UnityAdapter(Adapter):
    def __init__(self) -> None:
        super().__init__(
            "Unity",
            True,
            "Requires a matching Unity Editor with Android Build Support. A Windows player is not a project.",
        )

    def plan_command(self, version: str | None = None) -> str | None:
        return (
            "Unity -batchmode -quit -projectPath <project> "
            "-buildTarget Android -executeMethod AndroidBatch.Build -logFile -"
        )


class UnrealAdapter(Adapter):
    def __init__(self) -> None:
        super().__init__(
            "Unreal Engine",
            True,
            "Requires RunUAT from the EngineAssociation install. Cooked Windows content is not an Android cook.",
        )

    def plan_command(self, version: str | None = None) -> str | None:
        return (
            "RunUAT BuildCookRun -project=<Game>.uproject -platform=Android "
            "-clientconfig=Development -cook -stage -pak"
        )


class GodotAdapter(Adapter):
    def __init__(self) -> None:
        super().__init__(
            "Godot",
            True,
            "Requires the same editor version, Android export templates, and a named export preset.",
        )

    def plan_command(self, version: str | None = None) -> str | None:
        return 'godot --headless --export-release "Android" build/game.apk'


class UnsupportedAdapter(Adapter):
    def __init__(self, engine_id: str, notes: str) -> None:
        super().__init__(engine_id, False, notes)


ADAPTERS: dict[str, Adapter] = {
    "Unity": UnityAdapter(),
    "Unreal Engine": UnrealAdapter(),
    "Godot": GodotAdapter(),
    "GameMaker": Adapter(
        "GameMaker", True, "Android export stays inside the GameMaker IDE. A .yyp is not an APK."
    ),
    "Ren'Py": Adapter(
        "Ren'Py",
        True,
        "Use Ren'Py's RAPT packaging from the matching SDK. This worker does not download it.",
    ),
    "Defold": Adapter(
        "Defold", True, "Bundle with the Defold editor or bob.jar after the Android SDK path is set."
    ),
    "LibGDX": Adapter(
        "LibGDX", True, "Build the android Gradle module. Do not ship LWJGL desktop natives."
    ),
    "Cocos": Adapter(
        "Cocos",
        True,
        "Use Cocos Creator publish or the Cocos2d-x Android CMake toolchain.",
    ),
    "RPG Maker": UnsupportedAdapter(
        "RPG Maker",
        "No official APK exporter. HTML5 can be wrapped later in a real WebView project.",
    ),
    "HTML5": UnsupportedAdapter(
        "HTML5", "A WebView shell is a separate Android project. This worker does not generate one."
    ),
    "Electron": UnsupportedAdapter("Electron", "Electron has no Android target."),
    "LÖVE": UnsupportedAdapter("LÖVE", "No first-party Android exporter is invoked."),
    "MonoGame": Adapter(
        "MonoGame", False, "Android is a retarget, not a binary conversion."
    ),
    "Java": Adapter(
        "Java",
        False,
        "A JAR is not an Android project unless an Android Gradle module exists.",
    ),
    ".NET": UnsupportedAdapter(".NET", "CLR images are not converted to DEX."),
    "Custom C/C++": Adapter(
        "Custom C/C++",
        False,
        "Needs an NDK or CMake Android toolchain written by the project, not guessed.",
    ),
    "Android": Adapter(
        "Android",
        False,
        "Already an Android package or project. Validation does not rebuild it.",
    ),
    "Unknown": UnsupportedAdapter("Unknown", "No adapter claimed this input."),
}


def adapter_for(engine: str) -> Adapter:
    return ADAPTERS.get(engine, ADAPTERS["Unknown"])
