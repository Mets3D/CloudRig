# Well, this could probably be a lot more elegant.

from .rigs.cloud_utils import load_widget, make_name, slice_name

def create_parent_bone(self, child, shape=None):
    sliced_name = slice_name(child.name)
    sliced_name[1] += "_Parent"
    parent_name = make_name(*sliced_name)
    parent_bone = self.bone_infos.bone(
        parent_name, 
        child, 
        only_transform=True, 
        custom_shape_scale=1.1,
        **self.defaults
    )

    child.parent = parent_bone
    return parent_bone

# DSP bones - Display bones at the mid-point of each bone to use as display transforms for FK.
def create_dsp_bone(self, parent):
    """If Display Centered rig option is enabled, we want certain controls to display in the center of the bone rather than at the head."""
    if not self.params.display_middle: return
    dsp_name = "DSP-" + parent.name
    dsp_bone = self.bone_infos.bone(
        dsp_name, 
        parent, 
        custom_shape=None, 
        parent=parent
    )
    dsp_bone.put(parent.center, 0.1, 0.1)
    parent.custom_shape_transform = dsp_bone
    return dsp_bone