"""Conversion d'un montant entier (KMF, sans décimales) en toutes lettres françaises."""

_UNITES = [
    "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
    "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
]

_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_cent(n):
    if n == 0:
        return ""
    if n < 17:
        return _UNITES[n]
    if n < 20:
        return "dix-" + _UNITES[n - 10]
    if n < 70:
        dizaine, unite = divmod(n, 10)
        mot = _DIZAINES[dizaine]
        if unite == 0:
            return mot
        if unite == 1:
            return f"{mot} et un"
        return f"{mot}-{_UNITES[unite]}"
    if n < 80:
        if n == 71:
            return "soixante et onze"
        return "soixante-" + _moins_de_cent(n - 60)
    reste = n - 80
    if reste == 0:
        return "quatre-vingts"
    return "quatre-vingt-" + _moins_de_cent(reste)


def _moins_de_mille(n):
    if n < 100:
        return _moins_de_cent(n)
    centaine, reste = divmod(n, 100)
    prefixe = "cent" if centaine == 1 else f"{_UNITES[centaine]} cent"
    if reste == 0:
        return prefixe + ("s" if centaine > 1 else "")
    return f"{prefixe} {_moins_de_cent(reste)}"


def _groupe_avec_nom(n, singulier, pluriel):
    if n == 0:
        return ""
    if n == 1:
        return singulier if singulier == "mille" else f"un {singulier}"
    return f"{_moins_de_mille(n)} {pluriel}"


def nombre_en_lettres(n):
    n = int(n)
    if n == 0:
        return "zéro"
    if n < 0:
        return "moins " + nombre_en_lettres(-n)

    milliards, reste = divmod(n, 1_000_000_000)
    millions, reste = divmod(reste, 1_000_000)
    milliers, unites = divmod(reste, 1_000)

    parties = []
    if milliards:
        parties.append(_groupe_avec_nom(milliards, "milliard", "milliards"))
    if millions:
        parties.append(_groupe_avec_nom(millions, "million", "millions"))
    if milliers:
        parties.append(_groupe_avec_nom(milliers, "mille", "mille"))
    if unites:
        parties.append(_moins_de_mille(unites))

    return " ".join(p for p in parties if p)


def montant_en_lettres_kmf(montant):
    """Ex. 99981535 -> 'Quatre-vingt-dix-neuf millions neuf cent quatre-vingt-un mille
    cinq cent trente-cinq francs comoriens'."""
    mots = nombre_en_lettres(int(round(float(montant))))
    mots = mots[0].upper() + mots[1:]
    return f"{mots} francs comoriens"
