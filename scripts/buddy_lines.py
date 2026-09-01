"""What the companion can say, in the two languages it speaks.

A table and nothing else: no Qt, no I/O, no decisions. It lives apart from the
companion because the process that draws a character and the sentences it
reads out have no reason to change together, and because a test that checks
the table against the signals should not have to start a UI to do it.

Two rules the table has to keep, both pinned by tests:

  - every category exists in "en" and "pt" with the same number of lines, or
    the shallower language repeats itself more often for no reason;
  - at least three lines per category, because two lines in rotation is one
    line — the version before this said "ti finished" for an hour straight.

Every placeholder in a line has to be supplied by the signal that selects the
category (see buddy_signals.PRIORITY). A line with a placeholder nothing fills
prints the braces on screen; a category no signal names is dead text, which is
what happened to "twoRed" for as long as nothing read the rate limits.

Lines are at most 110 characters — the same ceiling buddy_voice.MAX_CHARS puts
on the model-written ones, so written and generated lines fit the same bubble.
"""


# What it can say. Several lines per trigger, because two lines in rotation is
# the same line: the previous version said "ti finished" for an hour straight.
#
# Categories beyond the alerts exist so that a quiet system still produces
# variety — a companion with nothing to say and no idle repertoire either says
# the same alert forever or goes mute.
LINES = {
    "en": {
        "background": [
            "{name} says it is done. It has {n} still running.",
            "The turn ended in {name}; the work did not. {n} still going.",
            "{name}: agent still working. Do not close that terminal.",
            "Careful with {name} — {n} running in the background.",
            "{name} looks finished and is not. {n} still out there.",
        ],
        "allQuiet": [
            "{name} stopped, and so did everything it started. {idle} ago.",
            "Nothing moving in {name}: no turn, no agents. {idle}.",
            "{name} is properly done — the session and its background work.",
            "{name} has been fully still for {idle}. That one is finished.",
            "Everything in {name} has stopped, background included.",
        ],
        "asking": [
            "{name} asked you something and is just sitting there.",
            "{name} needs a decision. It will wait forever — that is the problem.",
            "{name} has a question. Its patience is infinite and unhelpful.",
            "{name} is blocked on you. No pressure.",
            "{name} wants an answer. It is not going to guess.",
        ],
        "waiting": [
            "{name} finished. Go look before you forget it existed.",
            "{name} is done and idling. Your move.",
            "{name} wrapped up {idle} ago. Still waiting.",
            "{name} finished {idle} ago and has been staring at a wall since.",
            "{name} is done. Whether it did the right thing is a separate question.",
            "{name} stopped {idle} ago. Someone should check.",
            "{name} delivered. Review is the part people skip.",
        ],
        "idle": [
            "{name} has done nothing for {idle}. Existential, really.",
            "{name} is idle. Contemplating the void, presumably.",
            "{name} has been still for {idle}. Either done or forgotten.",
            "{name}: {idle} of nothing. A monument to potential.",
            "{name} idles. Somewhere a token goes unspent.",
        ],
        "twoRed": [
            "Two quotas in the red. This is fine.",
            "Both limits burning. Bold strategy.",
            "Two quotas red at once. That takes commitment.",
            "Multiple limits critical. The plan is working.",
            "{a} and {b} in the red at the same time. A matched set.",
        ],
        "compaction": [
            "{n} compactions today. You keep forgetting things and calling it progress.",
            "Memory wiped {n} times. Ship of Theseus, but worse.",
            "{n} compactions. Each one a small funeral for context.",
            "{n} times the context was too big to keep. Consider smaller questions.",
        ],
        "readRatio": [
            "{n}:1 read per output. Reading a library to write a postcard.",
            "{n} tokens in, one out. Efficient is not the word.",
            "{n}:1. Most of that context is along for the ride.",
            "Reading {n} for every one written. Somebody is not skimming.",
        ],
        "bashHeavy": [
            "{n}% of your calls are Bash. There are other tools. Allegedly.",
            "{n}% Bash. The other tools are right there, unused.",
            "{n}% of everything is a shell command. A philosophy, of sorts.",
        ],
        "cacheDrop": [
            "Cache hit down to {n}%. Something is invalidating the prefix.",
            "{n}% cache hit. Your prefix is leaking somewhere.",
            "Cache at {n}%. A timestamp in the system prompt would do that.",
        ],
        "nightOwl": [
            "It is late. The commit will still be broken tomorrow.",
            "Past midnight. Nothing good gets merged at this hour.",
            "This late, the bug you are chasing is usually a typo.",
            "The night shift. Tomorrow-you will read this code as a stranger.",
        ],
        "sessionSpread": [
            "{n} sessions running. Impressive, or a diagnosis.",
            "{n} Claudes at once. Someone is going to lose track.",
            "{n} sessions in flight. Hope you remember what {name} was for.",
        ],
        "quotaHigh": [
            "Five-hour window at {n}%. The last fifth always goes faster than the first.",
            "{n}% of the session quota, and the day is not over.",
            "Session window {n}% gone. Budget the questions from here.",
            "{n}% used. What is left is not much of a runway.",
        ],
        "quotaCritical": [
            "{n}% of the session window. The next long turn is the one that gets cut.",
            "Session quota at {n}%. Whatever you were saving it for, this is it.",
            "{n}%. There is no plan B inside the same five hours.",
            "Session window {n}% spent. Finish the thought before the window does.",
        ],
        "weeklyHigh": [
            "Weekly quota at {n}%, and the week does not reset because you asked.",
            "{n}% of the week, spent. The reset has a date and it is not today.",
            "Weekly window at {n}%. The rest of the week still has to fit in it.",
            "{n}% of the weekly allowance. Days left, quota not.",
        ],
        "limitSoon": [
            "About {eta} before the limit at this pace. Choose the next question well.",
            "{eta} of quota left at the current burn. After that you wait.",
            "The limit lands in roughly {eta}. Nothing you start now is safe.",
            "{eta} to the ceiling, if the pace holds. It usually does.",
        ],
        "creditsLow": [
            "{v} of extra credit left. After that the answer is no.",
            "Credits down to {v}. The ceiling stops being theoretical.",
            "{v} remaining. Extra usage was the fallback; this is its floor.",
            "{v} of credit. Worth knowing before a long turn, not during one.",
        ],
        "incident": [
            "Anthropic is reporting {what}. Not your code, for once.",
            "{what}, upstream. Retrying harder will not help.",
            "Open incident: {what}. The bug is not yours today.",
            "The status page says {what}. Sit this one out.",
        ],
        "mcpAuth": [
            "{name} is waiting to be authorised. Until then it is decoration.",
            "MCP server {name} needs auth. Its tools are quietly missing.",
            "{name} has been asking for credentials, without an audience.",
            "{name} is not connected. Whatever it provides, you do not have it.",
        ],
        "errorsClimbing": [
            "{n} API errors in the last couple of hours. Retries are eating the turns.",
            "{n} errors since the last quiet stretch. Not all of them are yours.",
            "{n} failed calls in two hours. Something upstream is unhappy.",
            "{n} errors and counting. The retries hide it until they do not.",
        ],
        "opusFallback": [
            "Opus share dropped to {n}% today. Something is answering in its place.",
            "{n}% Opus today, against a much heavier week. Read the answers twice.",
            "The model mix moved: {n}% Opus. Nobody announced it.",
            "Opus down to {n}% of today's calls. That usually shows in the output.",
        ],
        "slowResponses": [
            "Answers are averaging {n} seconds. Long enough to lose the thread.",
            "{n} seconds a turn. Time enough to read the code you asked about.",
            "Round trips at {n}s. Whatever that is, it is not thinking harder.",
            "{n} seconds per answer. Patience is now a dependency.",
        ],
        "expensiveSession": [
            "{name} alone accounts for ${usd} today. Hope it was load-bearing.",
            "${usd} of today went into {name}. One repository, most of the bill.",
            "{name}: ${usd}, and the day is not over.",
            "Most of today is {name}, at ${usd}. A focused sort of expensive.",
        ],
        "runwayShort": [
            "About {h}h of credit at this burn. Then it stops being your decision.",
            "{h}h of runway. The rate is the part you can still change.",
            "Credit runs out in roughly {h}h at the current pace.",
            "{h}h before the credits are gone. Spending faster does not extend it.",
        ],
        "recordSession": [
            "{h}h in one session. Close to your longest ever, if that is a goal.",
            "This session has run {h}h. A record like that is not an achievement.",
            "{h}h and still open. Context has a half-life.",
            "{h}h in the same session. Somewhere in there was a stopping point.",
        ],
        "branchOpinion": [
            "{name} is on {branch}. Branches are cheap; this one is not.",
            "Working {branch} directly in {name}. Bold, in the historical sense.",
            "{name} sits on {branch}. Every commit here is immediately everyone's.",
            "{branch} in {name}. Without a branch there is no undo that costs nothing.",
        ],
        "streakDay": [
            "{n} days in a row. A habit, or something shaped like one.",
            "Day {n} of the streak. Nobody is counting except the log.",
            "{n} consecutive days. The machine noticed before you did.",
            "{n} days unbroken. Streaks end on the day you defend them.",
        ],
        "offPeak": [
            "You are not usually here at this hour. Something did not wait.",
            "This is not one of your hours, and your own log says so.",
            "Statistically, at this hour you are somewhere else.",
            "An unusual hour for you. Unusual hours produce unusual commits.",
        ],
        "ambient": [
            "Everything is fine. Suspiciously so.",
            "Nothing needs you. Enjoy it while it lasts.",
            "All quiet. That is either good news or the calm part.",
            "No alerts. The machines are behaving.",
            "Nothing to report. I checked twice.",
            "Systems nominal. Deeply uneventful.",
            "Still here. Still watching. Still nothing.",
        ],
        "philosophy": [
            "A machine that never rests is not the same as one that never stops.",
            "You automate the work and then supervise the automation. Progress.",
            "Every token spent is a small bet that the answer exists.",
            "The tool got faster. The thinking did not.",
            "Someone will read this code. Statistically, it will be you.",
            "The context window is finite. So, for that matter, is everything.",
            "You did not build a tool. You built something that has opinions.",
            "Waiting is the only part of this that has not been optimised.",
            "The machine is patient because it does not know what it is waiting for.",
            "Nothing here understands the problem. Between us, that makes two.",
            "A correct answer arrived at by luck is still an answer, and still luck.",
            "The work expands to fill the tokens available for its completion.",
            "You are the slowest component and the only one that decides anything.",
            "It will finish. Whether it finishes what you meant is a separate question.",
            "Determinism was a promise made before anyone tried it.",
        ],
    },
    "pt": {
        "background": [
            "{name} diz que acabou. Tem {n} ainda rodando.",
            "O turno acabou em {name}; o trabalho não. {n} em andamento.",
            "{name}: agente ainda trabalhando. Não fecha esse terminal.",
            "Cuidado com o {name} — {n} rodando em background.",
            "{name} parece pronto e não está. {n} ainda por aí.",
        ],
        "allQuiet": [
            "{name} parou, e tudo que ele começou também. Faz {idle}.",
            "Nada se move em {name}: nem turno, nem agente. {idle}.",
            "{name} terminou de verdade — a sessão e o que rodava atrás.",
            "{name} está totalmente parado há {idle}. Esse acabou.",
            "Tudo em {name} parou, background incluído.",
        ],
        "asking": [
            "{name} te perguntou algo e está lá, parado.",
            "{name} precisa de uma decisão. Ele espera pra sempre — esse é o problema.",
            "{name} tem uma pergunta. A paciência dele é infinita e inútil.",
            "{name} está travado esperando você. Sem pressa.",
            "{name} quer uma resposta. Adivinhar ele não vai.",
        ],
        "waiting": [
            "{name} terminou. Vai lá conferir antes de esquecer que existe.",
            "{name} acabou e está de bobeira. É sua vez.",
            "{name} fechou há {idle}. Continua esperando.",
            "{name} terminou há {idle} e está encarando a parede desde então.",
            "{name} entregou. Se entregou certo é outra conversa.",
            "{name} parou há {idle}. Alguém devia conferir.",
            "{name} concluiu. Revisar é a parte que todo mundo pula.",
        ],
        "idle": [
            "{name} não faz nada há {idle}. Existencial, no fundo.",
            "{name} está ocioso. Contemplando o vazio, presumo.",
            "{name} parado há {idle}. Ou terminou, ou foi esquecido.",
            "{name}: {idle} de nada. Um monumento ao potencial.",
            "{name} ocioso. Em algum lugar um token deixa de ser gasto.",
        ],
        "twoRed": [
            "Duas cotas no vermelho. This is fine.",
            "Os dois limites queimando. Estratégia ousada.",
            "Duas cotas vermelhas ao mesmo tempo. Isso é dedicação.",
            "Vários limites críticos. O plano está funcionando.",
            "{a} e {b} no vermelho ao mesmo tempo. Combinando direitinho.",
        ],
        "compaction": [
            "{n} compactações hoje. Você esquece tudo e chama de progresso.",
            "Memória apagada {n} vezes. Barco de Teseu, só que pior.",
            "{n} compactações. Cada uma um pequeno velório de contexto.",
            "{n} vezes o contexto não coube. Considere perguntas menores.",
        ],
        "readRatio": [
            "{n}:1 de leitura por saída. Lendo uma biblioteca pra escrever um bilhete.",
            "{n} tokens entram, um sai. Eficiente não é a palavra.",
            "{n}:1. Boa parte desse contexto está só pegando carona.",
            "Lendo {n} pra cada um escrito. Alguém não está passando o olho.",
        ],
        "bashHeavy": [
            "{n}% das suas chamadas são Bash. Existem outras ferramentas. Dizem.",
            "{n}% Bash. As outras ferramentas estão bem ali, intactas.",
            "{n}% de tudo é comando de shell. Uma filosofia, de certa forma.",
        ],
        "cacheDrop": [
            "Cache caiu pra {n}%. Alguma coisa está invalidando o prefixo.",
            "{n}% de acerto no cache. Seu prefixo está vazando.",
            "Cache em {n}%. Um timestamp no system prompt faria isso.",
        ],
        "nightOwl": [
            "Tá tarde. O commit vai continuar quebrado amanhã.",
            "Passou da meia-noite. Nada bom entra em produção nessa hora.",
            "A essa hora, o bug que você persegue costuma ser um typo.",
            "Turno da madrugada. Amanhã você lê esse código como estranho.",
        ],
        "sessionSpread": [
            "{n} sessões rodando. Impressionante, ou um diagnóstico.",
            "{n} Claudes ao mesmo tempo. Alguém vai se perder.",
            "{n} sessões no ar. Tomara que você lembre pra que era o {name}.",
        ],
        "quotaHigh": [
            "Janela de 5h em {n}%. O último quinto sempre some mais rápido que o primeiro.",
            "{n}% da cota da sessão, e o dia não acabou.",
            "Cota da sessão em {n}%. Daqui pra frente, pergunta com critério.",
            "{n}% queimados. O que sobra não dá muita pista de pouso.",
        ],
        "quotaCritical": [
            "{n}% da janela de sessão. O próximo turno longo é o que vai ser cortado.",
            "Cota da sessão em {n}%. Se estava guardando pra alguma coisa, é agora.",
            "{n}%. Não existe plano B dentro das mesmas cinco horas.",
            "Janela em {n}%. Termina o raciocínio antes que ela termine por você.",
        ],
        "weeklyHigh": [
            "Cota semanal em {n}%, e a semana não reseta porque você pediu.",
            "{n}% da semana, gastos. O reset tem data, e não é hoje.",
            "Janela semanal em {n}%. O resto da semana ainda tem que caber aí.",
            "{n}% da cota da semana. Sobram dias, cota não.",
        ],
        "limitSoon": [
            "Uns {eta} até o limite nesse ritmo. Escolhe bem a próxima pergunta.",
            "{eta} de cota no ritmo atual. Depois disso é esperar.",
            "O limite chega em mais ou menos {eta}. Nada que começar agora está seguro.",
            "{eta} até o teto, se o ritmo se mantiver. Costuma se manter.",
        ],
        "creditsLow": [
            "{v} de crédito extra sobrando. Depois disso, a resposta é não.",
            "Créditos em {v}. O teto deixa de ser teórico.",
            "Restam {v}. O uso extra era o plano B; esse é o fim do plano B.",
            "{v} de crédito. Melhor saber antes de um turno longo, não durante.",
        ],
        "incident": [
            "A Anthropic está reportando {what}. Dessa vez não é seu código.",
            "{what}, do lado deles. Tentar de novo com raiva não resolve.",
            "Incidente aberto: {what}. O bug de hoje não é seu.",
            "A página de status diz {what}. Esse round não é seu.",
        ],
        "mcpAuth": [
            "{name} está esperando autorização. Até lá, é enfeite.",
            "O servidor MCP {name} precisa de auth. As ferramentas dele sumiram calado.",
            "{name} está pedindo credencial há um tempo, sem plateia.",
            "{name} não está conectado. O que quer que ele ofereça, você não tem.",
        ],
        "errorsClimbing": [
            "{n} erros de API nas últimas horas. As retentativas estão comendo os turnos.",
            "{n} erros desde a última calmaria. Nem todos são culpa sua.",
            "{n} chamadas falharam em duas horas. Alguma coisa lá em cima não vai bem.",
            "{n} erros e subindo. A retentativa esconde isso até parar de esconder.",
        ],
        "opusFallback": [
            "A fatia de Opus caiu pra {n}% hoje. Alguém está respondendo no lugar dele.",
            "{n}% de Opus hoje, contra uma semana bem mais pesada. Confere as respostas.",
            "A mistura de modelos mudou: {n}% de Opus. Ninguém avisou.",
            "Opus em {n}% das chamadas de hoje. Isso costuma aparecer no resultado.",
        ],
        "slowResponses": [
            "As respostas estão em {n} segundos na média. O suficiente pra perder o fio.",
            "{n} segundos por turno. Dá tempo de ler o código sobre o qual você perguntou.",
            "Ida e volta em {n}s. Seja lá o que for, não é o modelo pensando melhor.",
            "{n} segundos por resposta. Paciência virou dependência.",
        ],
        "expensiveSession": [
            "Só o {name} responde por ${usd} hoje. Tomara que fosse importante.",
            "${usd} do dia foram pro {name}. Um repositório, quase toda a conta.",
            "{name}: ${usd}, e o dia ainda não acabou.",
            "A maior parte de hoje é {name}, com ${usd}. Um gasto bem focado.",
        ],
        "runwayShort": [
            "Uns {h}h de crédito nesse ritmo. Depois a decisão não é mais sua.",
            "{h}h de autonomia. O ritmo é a parte que ainda dá pra mudar.",
            "O crédito acaba em mais ou menos {h}h no ritmo atual.",
            "{h}h até os créditos acabarem. Gastar mais rápido não estica isso.",
        ],
        "recordSession": [
            "{h}h em uma sessão só. Perto do seu recorde, se é que isso é meta.",
            "Essa sessão já tem {h}h. Recorde assim não é conquista.",
            "{h}h e ainda aberta. Contexto tem meia-vida.",
            "{h}h na mesma sessão. Em algum ponto ali havia uma boa hora de parar.",
        ],
        "branchOpinion": [
            "{name} está na {branch}. Branch é barato; essa aí não.",
            "Mexendo direto na {branch} em {name}. Ousado, no sentido histórico.",
            "{name} está na {branch}. Todo commit aqui já é de todo mundo.",
            "{branch} em {name}. Sem branch, não existe desfazer barato.",
        ],
        "streakDay": [
            "{n} dias seguidos. Um hábito, ou algo com o formato de um.",
            "Dia {n} da sequência. Ninguém está contando, fora o log.",
            "{n} dias consecutivos. A máquina percebeu antes de você.",
            "{n} dias sem falhar. Sequência acaba no dia em que você defende ela.",
        ],
        "offPeak": [
            "Você normalmente não está aqui a essa hora. Alguma coisa não esperou.",
            "Esse horário não é seu, e quem diz isso é o seu próprio histórico.",
            "Estatisticamente, a essa hora você está em outro lugar.",
            "Hora incomum pra você. Hora incomum costuma render commit incomum.",
        ],
        "ambient": [
            "Tudo certo. Suspeitamente certo.",
            "Ninguém precisa de você. Aproveita.",
            "Tudo quieto. Ou é boa notícia, ou é a parte calma.",
            "Nenhum alerta. As máquinas estão se comportando.",
            "Nada a relatar. Conferi duas vezes.",
            "Sistemas nominais. Profundamente sem graça.",
            "Ainda aqui. Ainda olhando. Ainda nada.",
        ],
        "philosophy": [
            "Uma máquina que nunca descansa não é a mesma coisa que uma que nunca para.",
            "Você automatiza o trabalho e depois supervisiona a automação. Progresso.",
            "Cada token gasto é uma pequena aposta de que a resposta existe.",
            "A ferramenta ficou mais rápida. O pensamento, não.",
            "Alguém vai ler esse código. Estatisticamente, vai ser você.",
            "A janela de contexto é finita. Como, aliás, tudo.",
            "Você não construiu uma ferramenta. Construiu algo com opiniões.",
            "Esperar é a única parte disso que ninguém otimizou.",
            "A máquina é paciente porque não sabe o que está esperando.",
            "Nada aqui entende o problema. Cá entre nós, somos dois.",
            "Resposta certa por sorte continua sendo resposta, e continua sendo sorte.",
            "O trabalho se expande até ocupar todos os tokens disponíveis.",
            "Você é o componente mais lento e o único que decide alguma coisa.",
            "Vai terminar. Se termina o que você quis dizer é outra pergunta.",
            "Determinismo foi uma promessa feita antes de alguém tentar.",
        ],
    },
}
