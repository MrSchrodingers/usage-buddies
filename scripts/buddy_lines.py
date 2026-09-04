"""What the companion can say, in the two languages it speaks.

A table and nothing else: no Qt, no I/O, no decisions. It lives apart from the
companion because the process that draws a character and the sentences it
reads out have no reason to change together, and because a test that checks
the table against the signals should not have to start a UI to do it.

Five rules the table has to keep, all five pinned by tests:

  - a category whose signal hands over a value says the value, in all eight
    lines. The version before this one left 133 of its 416 diagnostic lines
    without a number in them — 66 in English, 67 in Portuguese — and a
    diagnosis with the number taken out is an opinion: "days left, quota not"
    reads the same at thirty percent as at ninety, which is the whole of what
    "generic" meant when it was reported.
    The five categories that describe no measurement — ambient, philosophy,
    greeting, nightOwl, offPeak — carry no placeholder at all, and the test
    reads which categories are which from what the signals emit rather than
    from a list kept here, so a category added later joins one side or the
    other without anyone remembering to say so;
  - every category exists in "en" and "pt" with the same number of lines, or
    the shallower language repeats itself more often for no reason;
  - eight lines per category, because two lines in rotation is one line — the
    version before this said "ti finished" for an hour straight;
  - at most three lines in a category may be built as "clause. clause." The
    whole table used to be that shape, and a form repeated a hundred and
    thirty-nine times stops being a style and becomes a stutter. The rest have
    to be something else: one sentence, a question aimed at the person, a
    short reaction, a long sentence that breathes, or one that opens with a
    verb. tests/test_buddy_lines.py counts them;
  - the range of lengths gets used. A ceiling of 150 with every line at 100 is
    the same monotony measured against a different number, so each category
    carries at least one short line and at least one long one.

The register is second person. It talks *to* the person whose machine it lives
on: it can say hello, ask a question, or remark on what they are doing. That
inverts the rule the earlier version of this file and buddy_voice.SYSTEM both
stated ("never greet"), and the greeting category exists precisely because a
mascot that appears on a desktop and says nothing about arriving is furniture.

Registers are mixed inside every category on purpose, because one register for
thirty categories is the defect above wearing different words: a line that
carries a number and says what it means, a line that teaches something a
programmer would recognise, a line with a specific reference rather than vague
irony, and a line with a concrete thought about programming, waiting or the
cost of a decision. Nothing that would fit on a mug: a remark about finitude,
time or the fate of man says nothing about this desktop and could have been
written before the machine was switched on.

Every placeholder in a line has to be supplied by the signal that selects the
category (see buddy_signals.PRIORITY). A line with a placeholder nothing fills
prints the braces on screen; a category no signal names is dead text, which is
what happened to "twoRed" for as long as nothing read the rate limits.

"staleData" is the one category written to refuse rather than to report. Every
other line here asserts something about the machine on the strength of two
files, and nothing was reading their timestamps: a collector that dies leaves
the last figures on disk, and the companion went on quoting them with the same
confidence it had when they were minutes old. These eight say how old the
reading is and that no number follows from it, which is the only honest thing
a watcher can say once it has stopped watching.

Lines are at most 150 characters — the same ceiling buddy_voice.MAX_CHARS puts
on the model-written ones, so written and generated lines fit the same bubble.
The bubble word-wraps inside a fixed width and grows downwards, so the ceiling
is about how long a person will stand there reading, not about pixels.
"""


# What it can say. Eight lines per trigger, because two lines in rotation is
# the same line: the previous version said "ti finished" for an hour straight.
#
# Categories beyond the alerts exist so that a quiet system still produces
# variety — a companion with nothing to say and no idle repertoire either says
# the same alert forever or goes mute.
#
# "en" and "pt" are written separately rather than translated. A joke that
# survives translation is usually the one that was not doing much work.
LINES = {
    "en": {
        "greeting": [
            "Hello again.",
            "I am up and reading your quotas — say the word and I go back to being furniture.",
            "What are we breaking today?",
            "Booted. Nothing is on fire yet, which I will take as a good sign.",
            "A purple mascot with opinions about your rate limits: the nineties called and I let it ring.",
            "Good to see you.",
            "I read sessions.json and widget-data.json every few seconds, so anything I say about your usage came from a file you can open.",
            "You left me running. That is either trust or forgetfulness.",
        ],
        "background": [
            "{name} says done; {n} still running.",
            "Do not close {name}'s terminal.",
            "{name} called the turn finished while {n} of its own agents are still working, so what you are reading is not the whole answer yet.",
            "Killing {name}'s parent shell takes those {n} background agents with it.",
            "{name} looks finished and is not. {n} still out there.",
            "Did you look at what those {n} agents are doing in {name}?",
            "{n} things running in {name} with nobody watching them.",
            "The turn ended in {name}. The work did not.",
        ],
        "allQuiet": [
            "{name} is finished, session and background both.",
            "That is {name} finished.",
            "{name} stopped {idle} ago and nothing it started is still alive, which is the only version of finished that counts for anything.",
            "Anything left to check in {name}?",
            "{name} closed the loop. Rare enough to mention.",
            "No turn, no agents, no children: {name} is quiet all the way down.",
            "Nothing has moved in {name} for {idle}.",
            "{name} is done on both sides. The session and the work it left running.",
        ],
        "asking": [
            "{name} is waiting on you.",
            "Go answer {name}.",
            "{name} stopped mid-task to ask something and will sit there until a person types an answer, because it has nowhere else to be.",
            "Did you see that {name} is asking?",
            "{name} has a question. Its patience is infinite and unhelpful.",
            "A prompt with nobody in front of it is {name} holding a lock on your attention.",
            "{name} needs a decision from you, not from me.",
            "{name} is blocked on input. That is the one thing autonomy cannot do for you.",
        ],
        "waiting": [
            "{name} finished {idle} ago.",
            "Go look at {name}.",
            "The turn in {name} ended {idle} ago and nothing has read the diff since, which is the part that decides whether any of it was worth it.",
            "Did {name} do what you asked, or what you typed?",
            "{name} delivered. Confidence is not a review.",
            "Reviewing what {name} did is the step people skip when the output looks sure of itself.",
            "{name}: done {idle} ago, still unread.",
            "{name} wrapped up and is idling. Your move.",
        ],
        "idle": [
            "{name} has been still for {idle}, with an agent of its own still running somewhere.",
            "{name}: quiet, not finished.",
            "Something {name} started {idle} ago is still going, and the session has nothing to say about it, because background work reports to nobody.",
            "Is {name} waiting for you or for itself?",
            "{name} idles while its own subprocess works. Delegation, of a sort.",
            "Quiet for {idle} is not the same as done while a child of {name} still holds the file.",
            "{name} stopped. What it launched did not.",
            "A parent that exits before its children is how orphans reach init, and {name} has not exited yet.",
        ],
        "staleData": [
            "The last reading is {age} old.",
            "Nothing has been written for {age}, so I have nothing current to tell you.",
            "The collector stopped {age} ago and every number I hold is from before that, which makes reading them out a guess with a percent sign on it.",
            "{age} stale. I would rather say nothing than say it with confidence.",
            "Is the collector still running? Nothing new has landed in {age}.",
            "I am not quoting figures that are {age} out of date.",
            "A watcher that keeps reporting after its source dies is worse than a quiet one, and this one has been dead for {age}.",
            "No fresh data for {age}; the old figures are still on file and I am not going to pretend they are now.",
        ],
        "twoRed": [
            "{a} and {b} are both past ninety percent. This is fine.",
            "{a} and {b} in the red at once.",
            "{a} and {b} are both over ninety percent used, which means there is no window left to move the work into when one of them closes.",
            "{a} and {b}, same afternoon.",
            "When {a} and {b} go red together, the fallback is a clock rather than another model.",
            "Which one do you think resets first, {a} or {b}?",
            "{a} red, {b} red, nothing left to borrow from.",
            "Burning {a} and {b} down on one afternoon takes a certain kind of commitment.",
        ],
        "compaction": [
            "{n} compactions today.",
            "Each of those {n} is a lossy summary of the one before it.",
            "Compaction rewrote your context {n} times today, and a summary of a summary is how detail leaves without anyone deciding to drop it.",
            "{n} compactions. Ship of Theseus, with worse documentation.",
            "After {n} compactions, do you still know what this session originally asked for?",
            "{n} times the window filled up: smaller questions are allowed.",
            "Split the task in two and the count stops at {n}.",
            "{n} rewrites of the same memory, each one shorter than the one before.",
        ],
        "readRatio": [
            "{n}:1, read to written.",
            "{n}:1 is reading a library to write a postcard.",
            "For every token this writes, {n} go in, and you pay the reading side of that ratio on every turn after the one that opened the file.",
            "{n} tokens in, one out. Efficient is not the word.",
            "At {n}:1, does it need the whole file or the forty lines around the bug?",
            "Input is cheaper than output per token, which is exactly why {n}:1 stops looking alarming and starts looking like a habit.",
            "{n}:1 — most of that context is along for the ride.",
            "Point it at a range instead of a file and {n}:1 comes down on its own.",
        ],
        "bashHeavy": [
            "{n}% of your calls are Bash.",
            "{n}% Bash, and the other tools are right there.",
            "{n}% of every tool call today was a shell command, which works until one of them is not idempotent and the retry runs it twice.",
            "{n}% Bash. There are other tools, allegedly.",
            "Is grep faster than the rest, or is {n}% what familiar looks like?",
            "{n}% of your calls went through a thing with no schema, so nothing checked them before they ran.",
            "{n}% shell: a philosophy, of sorts.",
            "At {n}% the hammer has a pipe in it and everything downstream looks like a pipeline.",
        ],
        "cacheDrop": [
            "Cache hit at {n}%.",
            "Something is invalidating the prefix and holding you at {n}%.",
            "The cache matches on an exact prefix, so one changed byte near the front of the prompt misses everything after it, and yours is at {n}%.",
            "{n}% cache hit. A timestamp in the system prompt would do that.",
            "What did you add to the top of the prompt to get a {n}% hit rate?",
            "Prefix caching is all or nothing per block: {n}% means most blocks are being rebuilt.",
            "{n}% is paid for in latency before it is paid for in tokens.",
            "Move the volatile part to the end and {n}% starts climbing.",
        ],
        "nightOwl": [
            "It is late.",
            "The commit will still be broken tomorrow.",
            "Past midnight the bug you are chasing is a typo more often than it is a race condition, and you are the wrong person to tell them apart.",
            "Late. Nothing good gets merged at this hour.",
            "One more, then bed?",
            "Tomorrow-you reads this code as a stranger, and the stranger has no context window.",
            "The night shift writes the code the morning shift reverts.",
            "Go to sleep.",
        ],
        "sessionSpread": [
            "{n} sessions running.",
            "Someone is going to lose track of {n} of these.",
            "There are {n} sessions open at once, each holding half an idea only you can tell apart, including whatever {name} was originally for.",
            "{n} at once. Impressive, or a diagnosis.",
            "Quick: what is {name} doing right now?",
            "Switching between {n} of them costs more than the switch, because what it really costs is the reload.",
            "{n} Claudes, one you.",
            "Close the two of the {n} you have already forgotten about.",
        ],
        "quotaHigh": [
            "Session window at {n}%.",
            "{n}% of the five-hour window is gone, and the window is not interested in what you still had planned for it.",
            "At {n}% the fifth that is left is about one long turn plus the reading of what it returns.",
            "How much of that {n}% was re-reading the same file?",
            "{n}% used. The last fifth always goes faster than the first.",
            "Budget the questions from {n}% onwards.",
            "A window at {n}% is not a warning, it is arithmetic: what is left is what is left.",
            "{n}%, and the day is not over.",
        ],
        "quotaCritical": [
            "{n}% of the session window.",
            "{n}%: finish the thought.",
            "At {n}% the next long turn is the one that gets cut in the middle, and a cut turn spends the tokens without leaving you the answer.",
            "{n}% gone. Whatever you were saving it for, this is it.",
            "At {n}% used, is there anything here that has to happen before the reset?",
            "At {n}% there is no plan B inside the same five hours.",
            "{n}% used, and no second window to fail over to.",
            "Write the state somewhere a restart can read it, because {n}% leaves no room for a second attempt.",
        ],
        "weeklyHigh": [
            "Weekly window at {n}%.",
            "{n}% of the week is spent and the reset has a date, which is not the same as having a plan for the days between now and then.",
            "Days left; {n}% of the quota already gone.",
            "{n}% spent: the rest of the week runs on the remainder.",
            "{n}% of the weekly allowance. The calendar does not negotiate.",
            "Which of the jobs inside that {n}% actually needed the big model?",
            "At {n}% the ceiling has already turned every busy day left in the week into a smaller one.",
            "Spread what is left of the {n}%, or spend it and wait for the reset.",
        ],
        "limitSoon": [
            "{eta} left at this pace.",
            "Nothing longer than {eta} is safe to start.",
            "At the current burn the limit lands in {eta}, which is less than one long turn plus the time it takes to read what it returns.",
            "{eta} to the ceiling. Choose the next question well.",
            "Do you want the last {eta} going to this, or to the thing you came here for?",
            "Write down where you are while you still have {eta} to do it in.",
            "{eta} is a straight line drawn through a jagged afternoon, so read it as the optimistic end rather than as the number.",
            "{eta} of quota, and after that it is a clock instead of a decision.",
        ],
        "creditsLow": [
            "{v} of extra credit left.",
            "After {v}, the answer is no.",
            "Extra usage was the fallback and {v} is what is left of the fallback, so the next long turn is the one that spends the end of it.",
            "Credit at {v}. The ceiling stops being theoretical.",
            "Do you want the rest of {v} going to this, or to tomorrow?",
            "Measure {v} against the length of the next turn before you start it, not halfway through.",
            "{v} is a balance, not a rate — it says nothing about how fast it is leaving.",
            "The plan B has {v} of plan B left in it.",
        ],
        "incident": [
            "Anthropic is reporting {what}.",
            "{what}, and not your code for once.",
            "The status page says {what}, which means the retry loop you were about to write has already been written by someone upstream.",
            "They are calling it {what}. Retrying angrily does not fix someone else's server.",
            "Want to go read something until {what} clears?",
            "Open incident: {what}.",
            "{what} is the server saying it is full, not your client saying it asked wrong.",
            "Upstream, and the name they gave it is: {what}.",
        ],
        "mcpAuth": [
            "{name} is waiting to be authorised.",
            "Until {name} has a token it is decoration.",
            "The MCP server {name} is connected but not authorised, so its tools are missing from the list and nothing announces that they are missing.",
            "{name} wants credentials. It has been asking without an audience.",
            "Do you still use {name}, or does it only exist in the config?",
            "Run /mcp and give {name} its token.",
            "Whatever {name} exposes is missing from the tool list, and a tool that is not listed is one the model never thinks of.",
            "{name}: authorised nowhere, listed everywhere.",
        ],
        "errorsClimbing": [
            "{n} API errors in two hours.",
            "{n} retries are eating your turns.",
            "There were {n} failed calls in the last two hours, and every retry that hides one of them charges you the wait twice without saying so.",
            "{n} errors and climbing. The retry hides it until it stops hiding it.",
            "Do those {n} failures feel slow to you, or do they feel broken?",
            "Exponential backoff turned {n} errors into a queue rather than a crash, which is why nothing looks wrong from where you sit.",
            "{n} errors since the last quiet stretch, and not all of them are yours.",
            "Stop blaming the prompt for {n} network failures.",
        ],
        "opusFallback": [
            "Opus is {n}% of today's calls.",
            "At {n}% Opus, read the answers twice.",
            "Opus dropped to {n}% of today against a much heavier week, which usually means something smaller has been answering in its voice.",
            "{n}% Opus today. Nobody announced the change.",
            "Did you drop Opus to {n}%, or did something drop it for you?",
            "A slide to {n}% shows up in the output before anyone finds it in the settings.",
            "{n}% Opus: the mix moved and the prompts did not.",
            "Before rewriting the prompt, find out what is answering while Opus sits at {n}%.",
        ],
        "slowResponses": [
            "Answers averaging {n} seconds.",
            "{n} seconds is long enough to lose the thread.",
            "Round trips of {n} seconds are long enough that you start a second task, and what that costs is the context in your head, not the one in the window.",
            "{n} seconds a turn. That is not the model thinking harder.",
            "Got something to read for the {n} seconds this takes to come back?",
            "Those {n} seconds are per call; the wait you feel is per turn, and a turn is several of those calls stacked end to end.",
            "{n} seconds each, and the average is hiding the worst of them.",
            "{n}s round trips. Patience became a dependency.",
        ],
        "expensiveSession": [
            "{name} is ${usd} of today.",
            "One repository, ${usd} of the bill.",
            "{name} accounts for ${usd} today, more than half of everything, so whatever it was doing it was doing at full price.",
            "${usd} in {name}. Hope it was load-bearing.",
            "Was {name} worth ${usd} to you, or only to the loop?",
            "Cost concentrates where the context is largest, which is how ${usd} ended up in {name} rather than where the work was hardest.",
            "{name}: ${usd}, and the day is not over.",
            "Split {name} before it splits the budget again.",
        ],
        "runwayShort": [
            "About {h}h of credit at this burn.",
            "After {h}h it stops being your decision.",
            "The projection divides what is left by what you have been spending per hour, so {h}h is a straight line drawn through a very jagged afternoon.",
            "{h}h of runway. The rate is the part you can still change.",
            "Would you rather {h}h ran out before dinner or after?",
            "Spending faster does not extend {h}h.",
            "{h}h left, and a queue of long turns is the fastest way to make it fewer.",
            "Runway is balance over burn: halve the burn and {h}h becomes twice that.",
        ],
        "recordSession": [
            "{h}h in one session.",
            "{h}h: close to your longest ever.",
            "This session has been open for {h} hours, which is long enough that the beginning of it has already been compacted out of the middle.",
            "{h}h and still open. Context has a half-life.",
            "Do you remember what the first message of these {h}h asked for?",
            "{h}h measures the session, not the work that happened inside it.",
            "In {h}h a session does not accumulate understanding, it accumulates summary, and the summary is what gets carried forward.",
            "Open a new session and paste in the three things from these {h}h that matter.",
        ],
        "branchOpinion": [
            "{name} is on {branch}.",
            "Branches are cheap; the one you are standing on, {branch}, is not.",
            "You are committing straight to {branch} in {name}, where every commit is immediately everyone's and the undo is a revert with your name on it.",
            "{branch} in {name}. Bold, in the historical sense.",
            "Would you approve this diff if someone else had pushed it to {branch}?",
            "A branch is a name for a commit and costs a pointer; a commit on {branch} costs a revert.",
            "{name} on {branch}, with no cheap way back.",
            "Branch off {branch} first, then be brave.",
        ],
        "streakDay": [
            "{n} days in a row.",
            "The log counted {n} before you did.",
            "That is {n} consecutive days with something recorded, which says more about the habit than about any one of the days inside it.",
            "Day {n}. Nobody is counting except the log.",
            "Is {n} days a streak, or a schedule nobody asked you to agree to?",
            "Streaks end on the day you start defending them, and {n} is about where the defending starts.",
            "{n} days unbroken, and the counter has no opinion about the code.",
            "Take a day off and see what {n} was actually holding together.",
        ],
        "offPeak": [
            "Not one of your hours.",
            "Your own history says you are usually somewhere else right now.",
            "This hour sits outside the block your own log calls the working day, and odd hours are where the commits nobody remembers writing come from.",
            "An odd hour for you. Something did not wait.",
            "Did this have to happen now?",
            "The histogram of your last few weeks has no bar here.",
            "Off your usual hours, by your own data rather than my opinion.",
            "Whatever this is, it will still be here at ten.",
        ],
        "ambient": [
            "All quiet.",
            "Nothing needs you, which is a state worth noticing while it lasts.",
            "No alerts, no questions, nothing in the red — the whole board is dull and I have checked it twice.",
            "Everything is fine. Suspiciously fine.",
            "Enjoying the quiet, or looking for something to break?",
            "Nothing to report.",
            "Machines behaving. Deeply uneventful.",
            "Still here, still watching, still nothing.",
        ],
        "philosophy": [
            "You are the slowest part of this loop and the only part that decides anything.",
            "Reading code is harder than writing it, which is why so much of it gets rewritten instead of read.",
            "It will finish. Whether it finishes what you meant is a different question.",
            "A four-second wait is a pause; a forty-second wait is a context switch.",
            "Every prompt is a guess about which forty lines of the repository matter, and most of the cost is in guessing wide.",
            "Automating the work does not remove it. It moves you from doing it to reviewing it.",
            "Nobody meters attention.",
            "The expensive part was never the answer, it is deciding whether the answer is right.",
        ],
    },
    "pt": {
        "greeting": [
            "Voltei.",
            "Subi aqui. Nada pegando fogo por enquanto.",
            "O que a gente quebra hoje?",
            "Sou um mascote roxo com opinião sobre a sua cota; a parte do adware ficou nos anos 2000.",
            "Leio o sessions.json e o widget-data.json a cada poucos segundos, então tudo que eu falar de uso saiu de um arquivo que você pode abrir.",
            "Bom te ver.",
            "Me deixou rodando de novo. Ou é confiança, ou é esquecimento.",
            "Estou de olho nas suas janelas de cinco horas e de sete dias, e vou comentar sem você pedir.",
        ],
        "background": [
            "{name} diz que acabou; {n} ainda rodando.",
            "Não fecha o terminal do {name}.",
            "O {name} deu o turno por encerrado com {n} agentes dele ainda trabalhando, então o que você está lendo ainda não é a resposta inteira.",
            "Matar o shell pai do {name} leva junto esses {n} agentes.",
            "{name} parece pronto e não está. Tem {n} lá fora.",
            "Você viu o que esses {n} agentes estão fazendo no {name}?",
            "{n} coisas rodando no {name} sem ninguém olhando.",
            "O turno acabou no {name}. O trabalho não.",
        ],
        "allQuiet": [
            "{name} terminou de verdade: a sessão e o que ela largou rodando.",
            "O {name} acabou.",
            "O {name} parou faz {idle} e nada que ele começou continua vivo, que é a única versão de terminado que vale alguma coisa.",
            "Sobrou algo pra conferir no {name}?",
            "{name} fechou o ciclo. Raro o bastante pra comentar.",
            "Sem turno, sem agente, sem processo filho: o {name} está quieto até embaixo.",
            "Nada se mexe no {name} há {idle}.",
            "{name} está pronto dos dois lados. O da sessão e o do que rodava atrás.",
        ],
        "asking": [
            "{name} está esperando por você.",
            "Vai responder o {name}.",
            "O {name} parou no meio pra perguntar uma coisa e vai ficar ali até alguém digitar a resposta, porque ele não tem outro lugar pra ir.",
            "Você viu que o {name} perguntou?",
            "{name} tem uma pergunta. A paciência dele é infinita e inútil.",
            "Um prompt sem humano na frente é o {name} segurando um lock na sua atenção.",
            "{name} precisa de uma decisão sua, não minha.",
            "{name} travado no input. É a única coisa que a autonomia não faz por você.",
        ],
        "waiting": [
            "{name} terminou faz {idle}.",
            "Vai olhar o {name}.",
            "O turno do {name} fechou faz {idle} e ninguém leu o diff desde então, que é justamente a parte que decide se aquilo valeu alguma coisa.",
            "O {name} fez o que você pediu ou o que você escreveu?",
            "{name} entregou. Confiança não é revisão.",
            "Revisar o que o {name} fez é o passo que todo mundo pula quando a saída parece segura de si.",
            "{name}: pronto faz {idle}, e ainda sem leitor.",
            "{name} acabou e está de bobeira. É sua vez.",
        ],
        "idle": [
            "{name} está parado há {idle}, com um agente dele ainda rodando em algum canto.",
            "{name}: quieto, não pronto.",
            "Alguma coisa que o {name} começou faz {idle} continua rodando, e a sessão não tem nada a dizer sobre isso, porque background não presta contas.",
            "O {name} está esperando você ou esperando ele mesmo?",
            "{name} ocioso enquanto o subprocesso dele trabalha. Delegação, de certo modo.",
            "Quieto há {idle} não é o mesmo que terminado enquanto um filho do {name} ainda segura o arquivo.",
            "{name} parou. O que ele lançou, não.",
            "Pai que sai antes dos filhos é como órfão vira problema do init, e o {name} nem saiu ainda.",
        ],
        "staleData": [
            "A última leitura tem {age}.",
            "Faz {age} que nada é escrito aqui, então não tenho nada atual pra te dizer.",
            "O coletor parou faz {age} e todo número que eu tenho é de antes disso, o que faz de ler eles em voz alta um palpite com sinal de porcentagem.",
            "{age} de atraso. Prefiro não falar a falar com confiança.",
            "O coletor ainda está de pé? Nada novo chegou faz {age}.",
            "Não vou citar número que está {age} desatualizado.",
            "Vigia que segue reportando depois que a fonte morreu é pior que vigia calado, e esse aqui está morto faz {age}.",
            "Sem dado novo faz {age}; os números velhos continuam no arquivo e eu não vou fingir que são de agora.",
        ],
        "twoRed": [
            "{a} e {b} passaram dos noventa por cento. This is fine.",
            "{a} e {b} no vermelho ao mesmo tempo.",
            "{a} e {b} estão os dois acima de noventa por cento, ou seja, não sobrou janela nenhuma pra onde empurrar o trabalho quando uma fechar.",
            "{a} e {b}, na mesma tarde.",
            "Quando {a} e {b} ficam vermelhos juntos, o plano B é um relógio e não outro modelo.",
            "Qual você acha que reseta primeiro, {a} ou {b}?",
            "{a} no vermelho, {b} no vermelho, nada pra pegar emprestado.",
            "Queimar {a} e {b} na mesma tarde exige um certo tipo de dedicação.",
        ],
        "compaction": [
            "{n} compactações hoje.",
            "Cada uma dessas {n} é um resumo com perda da anterior.",
            "A compactação reescreveu seu contexto {n} vezes hoje, e resumo de resumo é como o detalhe some sem ninguém ter decidido jogar ele fora.",
            "{n} compactações. Barco de Teseu, com documentação pior.",
            "Depois de {n} compactações, você ainda sabe o que essa sessão pediu lá no começo?",
            "{n} vezes a janela encheu: pergunta menor é permitida.",
            "Quebra a tarefa em duas e a conta para em {n}.",
            "{n} reescritas da mesma memória, cada uma menor que a anterior.",
        ],
        "readRatio": [
            "{n}:1 de leitura por saída.",
            "{n}:1 é ler uma biblioteca pra escrever um bilhete.",
            "Pra cada token escrito entram {n}, e o lado da leitura você paga em todo turno depois daquele em que o arquivo foi aberto.",
            "{n} tokens entram, um sai. Eficiente não é a palavra.",
            "Em {n}:1, precisa do arquivo inteiro ou das quarenta linhas em volta do bug?",
            "Entrada é mais barata que saída por token, e é exatamente por isso que {n}:1 deixa de assustar e vira hábito.",
            "{n}:1 — boa parte desse contexto está só pegando carona.",
            "Aponta pra uma faixa em vez do arquivo e {n}:1 cai sozinho.",
        ],
        "bashHeavy": [
            "{n}% das suas chamadas são Bash.",
            "{n}% de Bash, e as outras ferramentas estão bem ali.",
            "{n}% de tudo que você chamou hoje foi comando de shell, o que funciona até o dia em que um deles não é idempotente e a retentativa roda duas vezes.",
            "{n}% Bash. Existem outras ferramentas, dizem.",
            "O grep é mais rápido que o resto ou {n}% é só o que familiar parece?",
            "{n}% das suas chamadas passaram por uma coisa sem schema, então nada conferiu nenhuma delas antes de rodar.",
            "{n}% de shell: uma filosofia, de certo modo.",
            "Com {n}% o martelo tem um pipe e tudo depois dele parece pipeline.",
        ],
        "cacheDrop": [
            "Cache em {n}%.",
            "Alguma coisa está invalidando o prefixo e te segurando em {n}%.",
            "O cache casa por prefixo exato, então um byte diferente lá na frente do prompt derruba tudo que vem depois, e o seu está em {n}%.",
            "{n}% de acerto. Um timestamp no system prompt faz exatamente isso.",
            "O que você colocou no topo do prompt pra chegar em {n}% de acerto?",
            "Cache de prefixo é tudo ou nada por bloco: {n}% quer dizer que a maioria está sendo remontada.",
            "{n}% se paga em latência antes de se pagar em token.",
            "Move a parte volátil pro fim e {n}% começa a subir.",
        ],
        "nightOwl": [
            "Tá tarde.",
            "O commit vai continuar quebrado amanhã.",
            "Depois da meia-noite o bug que você persegue é typo mais vezes do que é race condition, e você é a pessoa errada pra notar a diferença.",
            "Tarde. Nada bom entra em produção a essa hora.",
            "Mais um e dorme?",
            "O você de amanhã lê esse código como estranho, e estranho não tem janela de contexto.",
            "O turno da madrugada escreve o código que o turno da manhã reverte.",
            "Vai dormir.",
        ],
        "sessionSpread": [
            "{n} sessões rodando.",
            "Alguém vai se perder em {n} dessas.",
            "São {n} sessões abertas ao mesmo tempo, cada uma segurando meia ideia que só você sabe diferenciar, incluindo o que quer que o {name} fosse.",
            "{n} de uma vez. Impressionante, ou um diagnóstico.",
            "Rápido: o que o {name} está fazendo agora?",
            "Trocar entre {n} delas custa mais que a troca, porque o que custa mesmo é a recarga.",
            "{n} Claudes, um você.",
            "Fecha as duas das {n} que você já esqueceu.",
        ],
        "quotaHigh": [
            "Janela de cinco horas em {n}%.",
            "Já foram {n}% da janela de cinco horas, e a janela não está nem aí pro que você ainda tinha planejado pra ela.",
            "Em {n}%, o quinto que sobra dá pra um turno longo e a leitura do que ele devolver.",
            "Quanto desses {n}% foi reler o mesmo arquivo?",
            "{n}% gastos. O último quinto sempre some mais rápido que o primeiro.",
            "Pergunta com critério de {n}% em diante.",
            "Janela em {n}% não é aviso, é aritmética: o que sobrou é o que sobrou.",
            "{n}%, e o dia não acabou.",
        ],
        "quotaCritical": [
            "{n}% da janela da sessão.",
            "{n}%: termina o raciocínio.",
            "Em {n}%, o próximo turno longo é o que vai ser cortado no meio, e turno cortado gasta os tokens sem te deixar a resposta.",
            "{n}% queimados. Se estava guardando pra alguma coisa, é agora.",
            "Com {n}% usados, tem alguma coisa aqui que precisa acontecer antes do reset?",
            "Em {n}% não existe plano B dentro das mesmas cinco horas.",
            "{n}% usados, e nenhuma segunda janela pra assumir.",
            "Anota o estado em algum lugar que sobreviva a um restart, porque {n}% não deixa espaço pra segunda tentativa.",
        ],
        "weeklyHigh": [
            "Janela semanal em {n}%.",
            "{n}% da semana já foram e o reset tem data, o que não é a mesma coisa que ter plano pros dias entre agora e ele.",
            "Ainda sobram dias; {n}% da cota, não.",
            "{n}% gastos: o resto da semana roda no que ficou.",
            "{n}% da cota da semana. O calendário não negocia.",
            "Quais das tarefas dentro desses {n}% precisavam mesmo do modelo grande?",
            "Em {n}%, o teto já transformou todo dia movimentado que sobrou da semana num dia menor.",
            "Distribui o que sobrou dos {n}%, ou gasta e espera o reset.",
        ],
        "limitSoon": [
            "{eta} de janela nesse ritmo.",
            "Nada mais longo que {eta} é seguro começar agora.",
            "No ritmo atual o limite chega em {eta}, que é menos de um turno longo somado ao tempo de ler o que ele devolve.",
            "{eta} até o teto. Escolhe bem a próxima pergunta.",
            "Quer gastar os últimos {eta} nisso ou naquilo que você veio fazer?",
            "Anota onde você parou enquanto ainda tem {eta} pra fazer isso.",
            "{eta} é uma reta passada por cima de uma tarde torta, então lê como o lado otimista e não como o número.",
            "{eta} de cota, e depois vira relógio em vez de decisão.",
        ],
        "creditsLow": [
            "{v} de crédito extra sobrando.",
            "Depois de {v}, a resposta é não.",
            "O uso extra era o plano B e {v} é o que sobrou do plano B, então o próximo turno longo é o que gasta o fim dele.",
            "Crédito em {v}. O teto deixa de ser teórico.",
            "Você quer o resto de {v} indo pra isso ou pra amanhã?",
            "Mede {v} contra o tamanho do próximo turno antes de começar ele, e não no meio.",
            "{v} é saldo, não ritmo — não diz nada sobre a velocidade com que está indo embora.",
            "O plano B tem {v} de plano B pela frente.",
        ],
        "incident": [
            "A Anthropic está reportando isto: {what}.",
            "{what}, e dessa vez não é o seu código.",
            "A página de status diz: {what}. Ou seja, aquele retry que você ia escrever já foi escrito por alguém do outro lado.",
            "Tentar de novo com raiva não conserta {what} do lado deles.",
            "Quer ler alguma coisa até {what} passar?",
            "Incidente aberto: {what}.",
            "{what} é o servidor dizendo que está cheio, não o seu cliente dizendo que perguntou errado.",
            "É do lado deles, e o nome que deram foi: {what}.",
        ],
        "mcpAuth": [
            "{name} está esperando autorização.",
            "Até o {name} ter um token, é enfeite.",
            "O servidor MCP {name} está conectado mas não autorizado, então as ferramentas dele somem da lista e nada avisa que sumiram.",
            "{name} quer credencial. Está pedindo faz tempo, sem plateia.",
            "Você ainda usa o {name} ou ele só existe no config?",
            "Roda /mcp e dá o token pro {name}.",
            "O que o {name} expõe está fora da lista de ferramentas, e ferramenta fora da lista é ferramenta que o modelo nunca lembra.",
            "{name}: autorizado em lugar nenhum, listado em todo lugar.",
        ],
        "errorsClimbing": [
            "{n} erros de API em duas horas.",
            "{n} retentativas estão comendo os seus turnos.",
            "Foram {n} chamadas com falha nas últimas duas horas, e cada retentativa que esconde uma delas te cobra a espera duas vezes sem avisar.",
            "{n} erros e subindo. A retentativa esconde até parar de esconder.",
            "Essas {n} falhas parecem lentidão pra você ou parecem quebra?",
            "O backoff exponencial virou {n} erros numa fila em vez de numa queda, e é por isso que daqui de dentro nada parece errado.",
            "{n} erros desde a última calmaria, e nem todos são culpa sua.",
            "Para de culpar o prompt por {n} falhas de rede.",
        ],
        "opusFallback": [
            "Opus está em {n}% das chamadas de hoje.",
            "Com o Opus em {n}%, confere as respostas duas vezes.",
            "A fatia de Opus caiu pra {n}% hoje contra uma semana bem mais pesada, o que costuma significar que alguém menor respondeu com a voz dele.",
            "{n}% de Opus hoje. Ninguém avisou da troca.",
            "Você derrubou o Opus pra {n}% ou derrubaram por você?",
            "Uma queda pra {n}% aparece no resultado antes de alguém achar ela na configuração.",
            "{n}% de Opus: a mistura mudou e os prompts não.",
            "Antes de reescrever o prompt, descobre o que responde enquanto o Opus fica em {n}%.",
        ],
        "slowResponses": [
            "Respostas em {n} segundos na média.",
            "{n} segundos é tempo suficiente pra perder o fio.",
            "Ida e volta de {n} segundos é longo o bastante pra você começar outra coisa, e o que isso custa é o contexto da sua cabeça, não o da janela.",
            "{n} segundos por turno. Isso não é o modelo pensando melhor.",
            "Tem o que ler durante os {n} segundos que isso leva pra voltar?",
            "Esses {n} segundos são por chamada; a espera que você sente é por turno, e turno é várias dessas chamadas em fila.",
            "{n} segundos cada, e a média está escondendo as piores.",
            "{n}s de ida e volta. Paciência virou dependência.",
        ],
        "expensiveSession": [
            "{name} é ${usd} do dia de hoje.",
            "Um repositório, ${usd} da conta.",
            "O {name} responde por ${usd} hoje, mais da metade de tudo, então seja lá o que ele estava fazendo, estava fazendo a preço cheio.",
            "${usd} no {name}. Tomara que fosse estrutural.",
            "O {name} valeu ${usd} pra você ou só pro loop?",
            "Custo se concentra onde o contexto é maior, e é assim que ${usd} foram parar no {name} em vez de onde o trabalho era difícil.",
            "{name}: ${usd}, e o dia não acabou.",
            "Divide o {name} antes que ele divida o orçamento de novo.",
        ],
        "runwayShort": [
            "Sobram {h}h de crédito nesse ritmo.",
            "Depois de {h}h a decisão não é mais sua.",
            "A projeção divide o que sobrou pelo que você gastou por hora, então {h}h é uma reta passada por cima de uma tarde bem irregular.",
            "{h}h de autonomia. O ritmo é a parte que ainda dá pra mudar.",
            "Você prefere que {h}h acabem antes ou depois do jantar?",
            "Gastar mais rápido não estica {h}h.",
            "{h}h, e uma fila de turnos longos é o jeito mais rápido de virar menos.",
            "Autonomia é saldo dividido por ritmo: metade do ritmo, e {h}h vira o dobro disso.",
        ],
        "recordSession": [
            "{h}h em uma sessão só.",
            "{h}h: perto do seu recorde.",
            "Essa sessão está aberta há {h} horas, tempo suficiente pro começo dela já ter sido compactado pra fora do meio.",
            "{h}h e ainda aberta. Contexto tem meia-vida.",
            "Você lembra o que a primeira mensagem dessas {h}h pediu?",
            "{h}h mede a sessão, não o trabalho que aconteceu dentro dela.",
            "Em {h}h uma sessão não acumula entendimento, acumula resumo, e é o resumo que segue pra frente.",
            "Abre uma sessão nova e cola as três coisas dessas {h}h que importam.",
        ],
        "branchOpinion": [
            "{name} está na {branch}.",
            "Branch é barato; a {branch} em que você está, não.",
            "Você está commitando direto na {branch} em {name}, onde todo commit já é de todo mundo e o desfazer é um revert com o seu nome nele.",
            "{branch} em {name}. Ousado, no sentido histórico.",
            "Você aprovaria esse diff se outra pessoa tivesse empurrado ele na {branch}?",
            "Branch é um nome pra um commit e custa um ponteiro; commit na {branch} custa um revert.",
            "{name} na {branch}, sem caminho barato de volta.",
            "Sai da {branch} primeiro, depois seja corajoso.",
        ],
        "streakDay": [
            "{n} dias seguidos.",
            "O log contou {n} antes de você.",
            "São {n} dias consecutivos com alguma coisa registrada, o que fala mais do hábito do que de qualquer um dos dias lá dentro.",
            "Dia {n}. Ninguém está contando, fora o log.",
            "{n} dias é uma sequência ou uma escala que ninguém te pediu pra aceitar?",
            "Sequência acaba no dia em que você começa a defender ela, e {n} é mais ou menos onde a defesa começa.",
            "{n} dias sem falhar, e o contador não tem opinião sobre o código.",
            "Tira um dia e vê o que esses {n} estavam segurando.",
        ],
        "offPeak": [
            "Esse horário não é seu.",
            "Seu próprio histórico diz que você costuma estar em outro lugar agora.",
            "Essa hora está fora do bloco que o seu log chama de dia de trabalho, e é de hora incomum que sai o commit que ninguém lembra de ter escrito.",
            "Hora estranha pra você. Alguma coisa não esperou.",
            "Isso precisava ser agora?",
            "O histograma das suas últimas semanas não tem barra nenhuma aqui.",
            "Fora do seu horário, pelos seus dados e não pela minha opinião.",
            "Seja lá o que for, continua aqui às dez.",
        ],
        "ambient": [
            "Tudo quieto.",
            "Ninguém precisa de você, e isso é um estado que vale notar enquanto dura.",
            "Nenhum alerta, nenhuma pergunta, nada no vermelho — o painel inteiro está sem graça e eu conferi duas vezes.",
            "Tudo certo. Suspeitamente certo.",
            "Aproveitando a calmaria ou procurando o que quebrar?",
            "Nada a relatar.",
            "Máquinas comportadas. Profundamente sem graça.",
            "Ainda aqui, ainda olhando, ainda nada.",
        ],
        "philosophy": [
            "Você é a parte mais lenta desse loop e a única que decide alguma coisa.",
            "Ler código é mais difícil que escrever, e é por isso que se reescreve tanta coisa em vez de ler.",
            "Vai terminar. Se termina o que você quis dizer é outra pergunta.",
            "Espera de quatro segundos é uma pausa; de quarenta, é troca de contexto.",
            "Todo prompt é um palpite sobre quais quarenta linhas do repositório importam, e quase todo o custo está em chutar largo.",
            "Automatizar o trabalho não tira ele. Move você de fazer pra revisar.",
            "Ninguém mede atenção.",
            "O caro nunca foi a resposta, é decidir se a resposta está certa.",
        ],
    },
}
