# ERP Pronutre — Firebase

Sistema de gestão da Pronutre (trading de commodities e insumos para nutrição animal), publicado em **https://pronutre-erp.web.app**.

| Arquivo | O que é |
|---|---|
| `public/index.html` | O sistema já ligado ao Firebase (login, banco por empresa, tempo real, offline). É aqui que as mudanças são feitas. |
| `sistema/prototipo-sem-firebase.html` | O mesmo sistema sem Firebase (igual ao protótipo do claude.ai), para testes. |
| `firestore.rules` | Regras de acesso por empresa, papel e matriz de acessos. Valem mesmo para quem tentar burlar a tela. |
| `.github/workflows/publicar.yml` | Publicação automática: `main` vai para o ar; cada pull request ganha link de teste por 7 dias. |

## Segredos do repositório (Settings › Secrets and variables › Actions)
- `FIREBASE_SERVICE_ACCOUNT`: conteúdo do .json da conta de serviço (Firebase › Configurações do projeto › Contas de serviço › Gerar nova chave privada).
- `FIREBASE_PROJECT_ID`: `pronutre-erp`.

## Primeiro acesso
Abra o endereço → **Primeiro acesso** com `sistemas@pronutre.com.br` → informe o nome. A empresa é criada zerada e você entra como Gestão. Depois cadastre contas bancárias (Configurações) e usuários (Cadastros › Usuários, com e-mail); cada pessoa cria a própria senha em **Primeiro acesso**.

## Observações
- Dados em `empresas/pronutre/...` (pronto para várias empresas no futuro).
- Funciona sem sinal; sair do sistema apaga os dados guardados no aparelho; sessão expira em 14 h.
- Anexos ainda ficam no aparelho de quem anexou (próxima etapa: servidor no PC).

## Aplicativos (Windows e Android)
- Gerados pelo workflow **Aplicativos** (roda quando muda algo em `apps/` ou pelo botão *Run workflow*). Ficam em https://pronutre-erp.web.app/baixar.
- Android: TWA assinado com `apps/android/pronutre.keystore` (não apagar: sem ela o app não atualiza). Digital em `public/.well-known/assetlinks.json`.
- Windows: Tauri (`apps/windows`), abre o site em janela própria.

## Computador servidor
- Pasta `computador-servidor/`: anexos e relatórios no PC, anexos antigos via Tailscale Funnel (porta 8788), cópia de hora em hora + completa à noite, cópia automática para o HD externo marcado. Instruções em `computador-servidor/LEIA-ME.txt`.
