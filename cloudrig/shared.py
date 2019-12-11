# Well, this could probably be a lot more elegant.

from .rigs.cloud_utils import load_widget, make_name, slice_name

from .definitions.driver import *

presets = {
	'PRESET01' : [(0.6039215922355652, 0.0, 0.0), (0.7411764860153198, 0.06666667014360428, 0.06666667014360428), (0.9686275124549866, 0.03921568766236305, 0.03921568766236305)],
	'PRESET02' : [(0.9686275124549866, 0.250980406999588, 0.0941176563501358), (0.9647059440612793, 0.4117647409439087, 0.07450980693101883), (0.9803922176361084, 0.6000000238418579, 0.0)],
	'PRESET03' : [(0.11764706671237946, 0.5686274766921997, 0.03529411926865578), (0.3490196168422699, 0.7176470756530762, 0.04313725605607033), (0.5137255191802979, 0.9372549653053284, 0.11372549831867218)],
	'PRESET04' : [(0.03921568766236305, 0.21176472306251526, 0.5803921818733215), (0.21176472306251526, 0.40392160415649414, 0.874509871006012), (0.3686274588108063, 0.7568628191947937, 0.9372549653053284)],
	'PRESET05' : [(0.6627451181411743, 0.16078431904315948, 0.30588236451148987), (0.7568628191947937, 0.2549019753932953, 0.41568630933761597), (0.9411765336990356, 0.364705890417099, 0.5686274766921997)],
	'PRESET06' : [(0.26274511218070984, 0.0470588281750679, 0.4705882668495178), (0.3294117748737335, 0.22745099663734436, 0.6392157077789307), (0.529411792755127, 0.3921568989753723, 0.8352941870689392)],
	'PRESET07' : [(0.1411764770746231, 0.4705882668495178, 0.3529411852359772), (0.2352941334247589, 0.5843137502670288, 0.4745098352432251), (0.43529415130615234, 0.7137255072593689, 0.6705882549285889)],
	'PRESET08' : [(0.29411765933036804, 0.4392157196998596, 0.4862745404243469), (0.41568630933761597, 0.5254902243614197, 0.5686274766921997), (0.6078431606292725, 0.760784387588501, 0.803921639919281)],
	'PRESET09' : [(0.9568628072738647, 0.7882353663444519, 0.0470588281750679), (0.9333333969116211, 0.760784387588501, 0.21176472306251526), (0.9529412388801575, 1.0, 0.0)],
	'PRESET10' : [(0.11764706671237946, 0.125490203499794, 0.1411764770746231), (0.2823529541492462, 0.2980392277240753, 0.33725491166114807), (1.0, 1.0, 1.0)],
	'PRESET11' : [(0.43529415130615234, 0.18431372940540314, 0.41568630933761597), (0.5960784554481506, 0.2705882489681244, 0.7450980544090271), (0.8274510502815247, 0.1882353127002716, 0.8392157554626465)],
	'PRESET12' : [(0.4235294461250305, 0.5568627715110779, 0.13333334028720856), (0.49803924560546875, 0.6901960968971252, 0.13333334028720856), (0.7333333492279053, 0.9372549653053284, 0.35686275362968445)],
	'PRESET13' : [(0.5529412031173706, 0.5529412031173706, 0.5529412031173706), (0.6901960968971252, 0.6901960968971252, 0.6901960968971252), (0.8705883026123047, 0.8705883026123047, 0.8705883026123047)],
	'PRESET14' : [(0.5137255191802979, 0.26274511218070984, 0.14901961386203766), (0.545098066329956, 0.3450980484485626, 0.06666667014360428), (0.7411764860153198, 0.41568630933761597, 0.06666667014360428)],
	'PRESET15' : [(0.0313725508749485, 0.19215688109397888, 0.05490196496248245), (0.1098039299249649, 0.26274511218070984, 0.04313725605607033), (0.2039215862751007, 0.38431376218795776, 0.16862745583057404)],
}

# layers
IK_MAIN = 0
IK_SECOND = 16
FK_MAIN = 3
FK_SECOND = 17
STRETCH = 2
FACE_PRIMARY = 3
FACE_SECOND = 19
FACE_TWEAK = 20
FINGERS = 5
HAIR = 6
CLOTHES = 7

BODY_MECH = 8
BODY_MECH_ADJUST = 9
BODY_DEFORM = 24
BODY_DEFORM_ADJUST = 25

HEAD_MECH = 11
HEAD_UNLOCKERS = 12
HEAD_DEFORM = 27
HEAD_HIERARCHY = 28

DSP = 10
PROPERTIES = 30
BLACK_BOX = 31

# Name : Params dictionary.
group_defs = {
    'Body: Main FK Controls' : {
        'normal' : presets['PRESET02'][0],
        'select' : presets['PRESET02'][1],
        'active' : presets['PRESET02'][2],
        'layers' : [FK_MAIN]
    },
    'DSP - Display Transform Helpers' : {
        'normal' : presets['PRESET07'][0],
        'select' : presets['PRESET07'][1],
        'active' : presets['PRESET07'][2],
        'layers' : [DSP]
    },
    'Body: IK - IK Mechanism Bones' : {
        'layers' : [BODY_MECH]
    },
    'Body: Main IK Controls' : {
        'normal' : presets['PRESET03'][0],
        'select' : presets['PRESET03'][1],
        'active' : presets['PRESET03'][2],
        'layers' : [IK_MAIN]
    },
    'Body: Main IK Controls Extra Parents' : {
        'normal' : presets['PRESET09'][0],
        'select' : presets['PRESET09'][1],
        'active' : presets['PRESET09'][2],
        'layers' : [IK_SECOND]
    },
    'Body: FK Helper Bones' : {
        'layers' : [BODY_MECH]
    },
    'Properties' : {
        'normal' : presets['PRESET03'][0],
        'select' : presets['PRESET03'][1],
        'active' : presets['PRESET03'][2],
        'layers' : [PROPERTIES]
    },
    'Body: STR - Stretch Controls' : {
        'normal' : presets['PRESET09'][0],
        'select' : presets['PRESET09'][1],
        'active' : presets['PRESET09'][2],
        'layers' : [STRETCH]
    },
    'Body: DEF - Limb Deform Bones' : {
        'layers' : [BODY_DEFORM]
    },
    'Body: STR-H - Stretch Helpers' : {
        'layers' : [BODY_MECH]
    },

}

def create_parent_bone(self, child, shape=None):
    sliced_name = slice_name(child.name)
    sliced_name[1] += "_Parent"
    parent_name = make_name(*sliced_name)
    parent_bone = self.bone_infos.bone(
        parent_name, 
        child, 
        only_transform=True, 
        custom_shape_scale=child.custom_shape_scale*1.2,
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
        name=dsp_name, 
        source=parent, 
        custom_shape=None, 
        parent=parent
    )
    dsp_bone.put(parent.center, scale=0.3, bbone_scale=1.5)
    dsp_bone.bone_group = 'DSP - Display Transform Helpers'
    parent.custom_shape_transform = dsp_bone
    return dsp_bone

def make_bbone_scale_drivers(armature, bi):
    my_d = Driver()
    my_d.expression = "var/scale"
    my_var = my_d.make_var("var")
    my_var.type = 'TRANSFORMS'
    
    var_tgt = my_var.targets[0]
    var_tgt.id = armature
    var_tgt.transform_space = 'WORLD_SPACE'
    
    scale_var = my_d.make_var("scale")
    scale_var.type = 'TRANSFORMS'
    scale_tgt = scale_var.targets[0]
    scale_tgt.id = armature
    scale_tgt.transform_space = 'WORLD_SPACE'
    scale_tgt.transform_type = 'SCALE_Y'
    
    # Scale In X/Y
    if (bi.bbone_handle_type_start == 'TANGENT' and bi.bbone_custom_handle_start):
        var_tgt.bone_target = bi.bbone_custom_handle_start

        var_tgt.transform_type = 'SCALE_X'
        bi.drivers["bbone_scaleinx"] = my_d.clone()

        var_tgt.transform_type = 'SCALE_Z'
        bi.drivers["bbone_scaleiny"] = my_d.clone()
    
    # Scale Out X/Y
    if (bi.bbone_handle_type_end == 'TANGENT' and bi.bbone_custom_handle_end):
        var_tgt.bone_target = bi.bbone_custom_handle_end
        
        var_tgt.transform_type = 'SCALE_Z'
        bi.drivers["bbone_scaleouty"] = my_d.clone()

        var_tgt.transform_type = 'SCALE_X'
        bi.drivers["bbone_scaleoutx"] = my_d.clone()

    ### Ease In/Out
    my_d = Driver()
    my_d.expression = "scale-Y"

    scale_var = my_d.make_var("scale")
    scale_var.type = 'TRANSFORMS'
    scale_tgt = scale_var.targets[0]
    scale_tgt.id = armature
    scale_tgt.transform_type = 'SCALE_Y'
    scale_tgt.transform_space = 'LOCAL_SPACE'

    Y_var = my_d.make_var("Y")
    Y_var.type = 'TRANSFORMS'
    Y_tgt = Y_var.targets[0]
    Y_tgt.id = armature
    Y_tgt.transform_type = 'SCALE_AVG'
    Y_tgt.transform_space = 'LOCAL_SPACE'

    # Ease In
    if (bi.bbone_handle_type_start == 'TANGENT' and bi.bbone_custom_handle_start):
        Y_tgt.bone_target = scale_tgt.bone_target = bi.bbone_custom_handle_start
        bi.drivers["bbone_easein"] = my_d.clone()

    # Ease Out
    if (bi.bbone_handle_type_end == 'TANGENT' and bi.bbone_custom_handle_end):
        Y_tgt.bone_target = scale_tgt.bone_target = bi.bbone_custom_handle_end
        bi.drivers["bbone_easeout"] = my_d.clone()