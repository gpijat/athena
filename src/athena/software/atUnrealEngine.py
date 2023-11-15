import unreal


class DefaultContext(object):

    __IS_RUNNING = False

    def __enter__(self):
        pass

    def __exit__(self, type, value, traceback):
        pass


def select(toSelect, replace=True):
    actorSubSystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    if replace:
        actorSubSystem.clear_actor_selection_set()

    for each in toSelect:
        actorSubSystem.set_actor_selection_state(each, True)


def getDisplay(object_):
    if isinstance(object_, unreal.Actor):
        return object_.get_actor_label()

    return str(object_)


def toViewportHUD(widget):
    pass
