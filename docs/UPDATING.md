# Atualizador Windows

A partir da 0.3.2, o instalador espera o PID do próprio app, não o processo pai.
O app só fecha depois que o instalador confirma que iniciou e verificou a cópia.
Arquivos temporários ficam em `%LOCALAPPDATA%/Kupotube/updates`, fora da pasta do
executável. Uma cópia no disco de destino é verificada antes de substituir o
arquivo, com backup e tentativas para lidar com bloqueios temporários do Windows.
Falhas deixam um `error.txt` e mostram um aviso, em vez de apenas fechar o app.

O workflow compila um executável PyInstaller de teste e valida passagem para o
instalador, substituição, reinício e limpeza enquanto o processo iniciador
permanece aberto. Esse teste é separado da verificação de inicialização do app.

## Recuperar atualização antiga que não reiniciou

Se a versão anterior baixou uma atualização mas não substituiu o executável,
reinicie o Windows para encerrar qualquer instalador antigo em espera e substitua
manualmente o executável pela release 0.3.2 ou superior. Após abrir a versão
corrigida, a pasta `kupotube-update-*` antiga pode ser removida. Não execute o
`install.ps1` antigo manualmente nem apague arquivos durante uma atualização.
Preferências e sessão em AppData são preservadas.
