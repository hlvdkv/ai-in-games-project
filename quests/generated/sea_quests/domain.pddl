(define (domain mythic_quest)
  (:requirements :strips :typing)
  (:types location item npc enemy stage gate)

  (:predicates
    (hero-at ?l - location)
    (path ?from - location ?to - location)
    (visited ?l - location)
    (hidden-route ?i - item ?from - location ?to - location)
    (alternate-path ?from - location ?to - location)
    (revealed-route ?from - location ?to - location)
    (unexamined-location ?l - location)
    (examined-location ?l - location)

    (item-at ?i - item ?l - location)
    (portable ?i - item)
    (has ?i - item)
    (weapon ?i - item)
    (optional-item ?i - item)
    (healing-item ?i - item)
    (discovered ?i - item)
    (unexamined-item ?i - item)
    (examined-item ?i - item)

    (npc-at ?n - npc ?l - location)
    (can-talk ?n - npc)
    (talked ?n - npc)
    (wants ?n - npc ?i - item)
    (gave ?i - item ?n - npc)
    (befriended ?n - npc)
    (angered ?n - npc)
    (provocation-open ?n - npc ?e - enemy ?l - location)
    (unexamined-npc ?n - npc)
    (examined-npc ?n - npc)

    (enemy-at ?e - enemy ?l - location)
    (hostile ?e - enemy)
    (defeated ?e - enemy)
    (optional-enemy ?e - enemy)
    (unexamined-enemy ?e - enemy)
    (examined-enemy ?e - enemy)

    (wounded)
    (healed-with ?i - item)

    (locked-gate ?g - gate ?from - location ?to - location)
    (unlocked ?g - gate)

    (ritual-site ?l - location)
    (ritual-complete ?i - item ?l - location)
    (threat-active)

    (current-stage ?s - stage)
    (next-stage ?s - stage ?n - stage)
    (travel-step ?from - location ?to - location ?s - stage ?n - stage)
    (take-step ?i - item ?l - location ?s - stage ?n - stage)
    (talk-step ?npc - npc ?l - location ?s - stage ?n - stage)
    (give-step ?i - item ?npc - npc ?l - location ?s - stage ?n - stage)
    (unlock-step ?g - gate ?key - item ?from - location ?to - location ?s - stage ?n - stage)
    (fight-step ?enemy - enemy ?l - location ?weapon - item ?s - stage ?n - stage)
    (ritual-step ?artifact - item ?l - location ?s - stage ?n - stage)
  )

  (:action travel
    :parameters (?from - location ?to - location ?s - stage ?n - stage)
    :precondition (and
      (current-stage ?s)
      (next-stage ?s ?n)
      (hero-at ?from)
      (path ?from ?to)
      (travel-step ?from ?to ?s ?n)
    )
    :effect (and
      (not (hero-at ?from))
      (hero-at ?to)
      (visited ?to)
      (not (current-stage ?s))
      (current-stage ?n)
    )
  )

  (:action take
    :parameters (?item - item ?loc - location ?s - stage ?n - stage)
    :precondition (and
      (current-stage ?s)
      (next-stage ?s ?n)
      (hero-at ?loc)
      (item-at ?item ?loc)
      (portable ?item)
      (take-step ?item ?loc ?s ?n)
    )
    :effect (and
      (has ?item)
      (discovered ?item)
      (not (item-at ?item ?loc))
      (not (current-stage ?s))
      (current-stage ?n)
    )
  )

  (:action talk
    :parameters (?npc - npc ?loc - location ?s - stage ?n - stage)
    :precondition (and
      (current-stage ?s)
      (next-stage ?s ?n)
      (hero-at ?loc)
      (npc-at ?npc ?loc)
      (can-talk ?npc)
      (talk-step ?npc ?loc ?s ?n)
    )
    :effect (and
      (talked ?npc)
      (not (current-stage ?s))
      (current-stage ?n)
    )
  )

  (:action give
    :parameters (?item - item ?npc - npc ?loc - location ?s - stage ?n - stage)
    :precondition (and
      (current-stage ?s)
      (next-stage ?s ?n)
      (hero-at ?loc)
      (npc-at ?npc ?loc)
      (has ?item)
      (wants ?npc ?item)
      (give-step ?item ?npc ?loc ?s ?n)
    )
    :effect (and
      (gave ?item ?npc)
      (befriended ?npc)
      (not (has ?item))
      (not (current-stage ?s))
      (current-stage ?n)
    )
  )

  (:action unlock
    :parameters (?gate - gate ?key - item ?from - location ?to - location ?s - stage ?n - stage)
    :precondition (and
      (current-stage ?s)
      (next-stage ?s ?n)
      (hero-at ?from)
      (has ?key)
      (locked-gate ?gate ?from ?to)
      (unlock-step ?gate ?key ?from ?to ?s ?n)
    )
    :effect (and
      (unlocked ?gate)
      (path ?from ?to)
      (path ?to ?from)
      (not (current-stage ?s))
      (current-stage ?n)
    )
  )

  (:action fight
    :parameters (?enemy - enemy ?loc - location ?weapon - item ?s - stage ?n - stage)
    :precondition (and
      (current-stage ?s)
      (next-stage ?s ?n)
      (hero-at ?loc)
      (enemy-at ?enemy ?loc)
      (hostile ?enemy)
      (weapon ?weapon)
      (has ?weapon)
      (fight-step ?enemy ?loc ?weapon ?s ?n)
    )
    :effect (and
      (defeated ?enemy)
      (not (hostile ?enemy))
      (not (current-stage ?s))
      (current-stage ?n)
    )
  )

  (:action ritual
    :parameters (?artifact - item ?loc - location ?s - stage ?n - stage)
    :precondition (and
      (current-stage ?s)
      (next-stage ?s ?n)
      (hero-at ?loc)
      (has ?artifact)
      (ritual-site ?loc)
      (ritual-step ?artifact ?loc ?s ?n)
    )
    :effect (and
      (ritual-complete ?artifact ?loc)
      (not (threat-active))
      (not (current-stage ?s))
      (current-stage ?n)
    )
  )

  (:action examine-location
    :parameters (?loc - location)
    :precondition (and
      (hero-at ?loc)
      (unexamined-location ?loc)
    )
    :effect (and
      (examined-location ?loc)
      (not (unexamined-location ?loc))
    )
  )

  (:action examine-item-at
    :parameters (?item - item ?loc - location)
    :precondition (and
      (hero-at ?loc)
      (item-at ?item ?loc)
      (unexamined-item ?item)
    )
    :effect (and
      (examined-item ?item)
      (not (unexamined-item ?item))
    )
  )

  (:action examine-carried-item
    :parameters (?item - item)
    :precondition (and
      (has ?item)
      (unexamined-item ?item)
    )
    :effect (and
      (examined-item ?item)
      (not (unexamined-item ?item))
    )
  )

  (:action examine-npc
    :parameters (?npc - npc ?loc - location)
    :precondition (and
      (hero-at ?loc)
      (npc-at ?npc ?loc)
      (unexamined-npc ?npc)
    )
    :effect (and
      (examined-npc ?npc)
      (not (unexamined-npc ?npc))
    )
  )

  (:action examine-enemy
    :parameters (?enemy - enemy ?loc - location)
    :precondition (and
      (hero-at ?loc)
      (enemy-at ?enemy ?loc)
      (hostile ?enemy)
      (unexamined-enemy ?enemy)
    )
    :effect (and
      (examined-enemy ?enemy)
      (not (unexamined-enemy ?enemy))
    )
  )

  (:action reveal-alternate-path
    :parameters (?item - item ?from - location ?to - location)
    :precondition (and
      (hero-at ?from)
      (has ?item)
      (hidden-route ?item ?from ?to)
    )
    :effect (and
      (path ?from ?to)
      (path ?to ?from)
      (alternate-path ?from ?to)
      (alternate-path ?to ?from)
      (revealed-route ?from ?to)
      (not (hidden-route ?item ?from ?to))
    )
  )

  (:action travel-alternate
    :parameters (?from - location ?to - location)
    :precondition (and
      (hero-at ?from)
      (path ?from ?to)
      (alternate-path ?from ?to)
    )
    :effect (and
      (not (hero-at ?from))
      (hero-at ?to)
      (visited ?to)
    )
  )

  (:action take-optional
    :parameters (?item - item ?loc - location)
    :precondition (and
      (hero-at ?loc)
      (item-at ?item ?loc)
      (portable ?item)
      (optional-item ?item)
    )
    :effect (and
      (has ?item)
      (discovered ?item)
      (not (item-at ?item ?loc))
    )
  )

  (:action press-npc
    :parameters (?npc - npc ?enemy - enemy ?loc - location)
    :precondition (and
      (hero-at ?loc)
      (npc-at ?npc ?loc)
      (enemy-at ?enemy ?loc)
      (provocation-open ?npc ?enemy ?loc)
    )
    :effect (and
      (angered ?npc)
      (hostile ?enemy)
      (not (provocation-open ?npc ?enemy ?loc))
    )
  )

  (:action brawl
    :parameters (?enemy - enemy ?loc - location)
    :precondition (and
      (hero-at ?loc)
      (enemy-at ?enemy ?loc)
      (hostile ?enemy)
      (optional-enemy ?enemy)
    )
    :effect (and
      (defeated ?enemy)
      (wounded)
      (not (hostile ?enemy))
    )
  )

  (:action use-healing-item
    :parameters (?item - item)
    :precondition (and
      (has ?item)
      (healing-item ?item)
      (wounded)
    )
    :effect (and
      (healed-with ?item)
      (not (wounded))
      (not (has ?item))
    )
  )
)
