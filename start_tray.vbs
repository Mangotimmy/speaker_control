Set FSO = CreateObject("Scripting.FileSystemObject")
scriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)

pythonwPath = "C:\Python314\pythonw.exe"
If Not FSO.FileExists(pythonwPath) Then
    pythonwPath = "pythonw.exe"
End If

cmd = """" & pythonwPath & """ """ & scriptDir & "\tray_app.py"""

Set objWMIService = GetObject("winmgmts:\\.\root\cimv2:Win32_Process")
objWMIService.Create cmd, scriptDir, Null, intProcessID
