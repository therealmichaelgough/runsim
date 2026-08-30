// Unreal Build Tool target for the standalone game.
using UnrealBuildTool;
using System.Collections.Generic;

public class RunsimViewerTarget : TargetRules
{
	public RunsimViewerTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("RunsimViewer");
	}
}
