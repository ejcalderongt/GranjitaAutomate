Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
python = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(python) Then
    MsgBox "Falta instalar el entorno. Consulta docs/version-1.md.", 48, "GranjitaAutomate"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
shell.Run Chr(34) & python & Chr(34) & " -m granjita", 1, False
