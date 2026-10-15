Kupotube 0.3.2

- Corrigida a espera pelo processo do atualizador: aguarda o app, não o processo pai que pode permanecer aberto.
- O app só fecha após o instalador confirmar que iniciou e verificou a cópia da atualização.
- Arquivos de atualização ficam em AppData, sem criar pasta ao lado do executável.
- Limpeza com tentativas adicionais e mensagens de erro para evitar falhas silenciosas.
- Teste Windows de atualização e reinício com um executável PyInstaller empacotado.

Como o atualizador antigo pode falhar antes de instalar esta correção, baixe esta versão manualmente se necessário.
