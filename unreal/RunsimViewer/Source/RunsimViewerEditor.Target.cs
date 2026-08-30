// Unreal Build Tool target for the editor.
using UnrealBuildTool;
using System.Collections.Generic;

public class RunsimViewerEditorTarget : TargetRules
{
	public RunsimViewerEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("RunsimViewer");
	}
}
