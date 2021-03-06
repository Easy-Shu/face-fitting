#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from mm.models import MeshModel
from mm.utils.io import exportObj
from mm.optimize.camera import initialRegistration
import mm.optimize.depth as opt
from mm.utils.mesh import generateFace

import os, json
import numpy as np
from scipy.interpolate import interpn
from scipy.optimize import minimize, check_grad, least_squares
from sklearn.neighbors import NearestNeighbors
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from mpl_toolkits.mplot3d import Axes3D
from pylab import savefig

if __name__ == "__main__":
    
    # Change directory to the folder that holds the VRN data, OpenPose landmarks, and original images (frames) from the source video
    os.chdir('/home/leon/f2f-fitting/data/obama/')
    
    # Input the number of frames in the video
    numFrames = 2882 #2260 #3744
    
    # Load 3DMM
    m = MeshModel('../../models/bfm2017.npz')
    
    # While looping through each frame in the video to fit the 3DMM, you might want to generate and save some matplotlib figures. In that case, uncomment the 'plt.ioff()' line to turn off interactive plotting so that the figure windows remain hidden. If you want to see the figure windows to debug code, then remember to set 'plt.ion()'.
#    plt.ion()
#    plt.ioff()
    
    # Initialize a (numFrames, numParameters) array to store the learned 3DMM parameters for each frame
    param = np.zeros((numFrames, m.numId + m.numExp + 7))
    
    # Initialize a (numFrames, 4) array to store the translation vector (3,) and scaling factor (1,) for each frame. During the loop, we fit the 3DMM to the VRN cropped and scaled image, so this array contains the information to transform the 3DMM back to the original image.
    TS2orig = np.zeros((numFrames, 4))
    
    # Set weights for the 3DMM vertex fitting, landmark fitting, and shape regularization terms
    wVer = 10
    wLan = 50
    wReg = 1
    
    # It is very important that you save the 'crop.tmp' file from the VRN fitting because we use it to find the correspondence between the original images and the cropped and scaled images produced by VRN
    with open('crop.tmp', 'r') as fd:
        crop = []
        for l in fd:
            crop.append([float(x) for x in l.split(' ')[1:]])
    crop = np.array(crop)
    
    # Loop through each frame in the video
    for frame in np.arange(1, numFrames + 1):
        print(frame)
        
        """
        Set filenames and read landmarks 
        """
        fName = '{:0>5}'.format(frame)
        
        # The VRN cropped and scaled images
        fNameImgScaled = 'scaled/' + fName + '.png'
        
        # The images/frames from the original video
        fNameImgOrig = 'orig/' + fName + '.png'
        
        # The volume files produced by VRN
        fNameVol = 'volume/' + fName + '.raw'
        
        # The OpenPose landmarks for each frame from the original video
        fNameLandmarks = 'landmark/' + fName + '.json'
        
        # Read the landmarks generated by OpenPose (it will be the .json condition)
        if fNameLandmarks.endswith('.txt'):
            with open(fNameLandmarks, 'r') as fd:
                lm = []
                for l in fd:
                    lm.append([int(coord) for coord in l.split(',')])
            lm = np.array(lm)
        elif fNameLandmarks.endswith('.json'):
            with open(fNameLandmarks, 'r') as fd:
                lm = json.load(fd)
            lm = np.array([l[0] for l in lm], dtype = int).squeeze()[:, :3]
            lmConf = lm[:, -1]  # This is the confidence value of the landmarks
            lm = lm[:, :2]
            
        # Load the original image, and you can choose to plot the OpenPose landmarks over the image
        imgOrig = mpimg.imread(fNameImgOrig)
#        plt.figure()
#        plt.imshow(imgOrig)
#        plt.scatter(lm[:, 0], lm[:, 1], s = 2)
#        plt.title(fName)
#        if not os.path.exists('landmarkPicOrig'):
#            os.makedirs('landmarkPicOrig')
#        savefig('landmarkPicOrig/' + fName + '.png', bbox_inches='tight')
#        plt.close('all')
#        continue
        
        '''
        Preprocess landmarks: map to VRN cropped/scaled version of images
        '''
        
        # Some parameters to map the landmarks from the original image to the VRN scaled and cropped image
        scale = 0.01 * crop[frame - 1, -1]
        cropCorner = np.rint(crop[frame - 1, :2])
        scaledImgDim = np.rint(np.array(imgOrig.shape[1::-1]) * scale)
        
        # Case 1: The cropped picture is contained within the scaled image
        if (cropCorner >= 0).all() and ((192 + cropCorner) < scaledImgDim).all():
            lmScaled = lm * scale - cropCorner
            case = 1
        
        # Case 2: The crop corner is outside of the scaled image, but the extent of the cropped picture is within the bounds of the scaled image
        elif (cropCorner < 0).any() and ((192 + cropCorner) < scaledImgDim).all():
            lmScaled = lm * scale - cropCorner * (cropCorner > 0) - cropCorner * (cropCorner < 0) / 2
            case = 2
        
        # Case 3: The crop corner is outside of the scaled image, and the extent of the cropped picture is beyond the bounds of the scaled image
        elif (cropCorner < 0).any() and ((192 + cropCorner) > scaledImgDim).any():
            lmScaled = lm * scale - cropCorner * (cropCorner > 0) + (192 - (scaledImgDim - cropCorner * (cropCorner > 0))) / 2
            case = 3
        
        # You can save the transformed version of the OpenPose landmarks that correspond to the cropped and scaled VRN images
#        np.save('landmarks_scaled/' + fName, lmScaled)
        
        # You can plot these scaled landmarks too
        imgScaled = mpimg.imread(fNameImgScaled)
#        fig, ax = plt.subplots()
#        plt.imshow(imgScaled)
#        plt.hold(True)
#        x = lmScaled[:, 0]
#        y = lmScaled[:, 1]
#        ax.scatter(x, y, s = 2, c = 'b', picker = True)
#        fig.canvas.mpl_connect('pick_event', onpick3)
        
#        plt.figure()
#        plt.imshow(imgScaled)
#        plt.scatter(lmScaled[:, 0], lmScaled[:, 1], s = 2)
#        plt.title(fName + '_' + str(case))
#        if not os.path.exists('landmarkPic'):
#            os.makedirs('landmarkPic')
#        savefig('landmarkPic/' + fName + '.png', bbox_inches='tight')
#        plt.close('all')
#        continue
        
        '''
        Processing the volume generated by VRN and generate the depth map that is used for 3DMM fitting
        '''
        
        # Import volume generated by VRN
        vol = np.fromfile(fNameVol, dtype = np.int8)
        vol = vol.reshape((200, 192, 192))
        
        # Take the max values of volume as the depth map and rescale the z-axis by 1/2
        depth = np.argmax(vol[::-1, :, :] > 0, axis = 0) / 2
        
        # You can save the depth map if you want
#        np.save('depth/' + fName, depth)
        
        # You can also plot the depth map
#        fig = plt.figure()
#        ax = plt.axes(projection='3d')
#        xv, yv = np.meshgrid(np.arange(192), np.arange(192))
#        ax.scatter(xv, yv, depth, s = 0.1, c = 'b')
#        ax.set_xlabel('X')
#        ax.set_ylabel('Y')
#        ax.set_zlabel('Z')
        
        # Where the depth map is equal to 0 (i.e., places where the face is not defined), we change these values to something arbitrary so that the nearest neighbors step below won't map landmarks to these values
        depth2 = depth.copy()
        depth2[depth == 0] = np.max(depth)
        
        # From the scaled version of the OpenPose landmarks, only keep the landmarks that we have a correspondence to with the 3DMM
        lmScaled = lmScaled[m.targetLMInd, :]
        
        # Project the 2D OpenPose landmarks onto the 3D depth map
        targetLandmarks = np.c_[lmScaled, interpn((np.arange(0, 192), np.arange(0, 192)), depth2, lmScaled[:, ::-1], method = 'nearest')]
        
        """
        Initial registration of similarity transform and shape coefficients
        """
        
        # For the first frame in the video...
        if frame == 1:
            # Find initial guess of the similarity transformation (rotation, translation, scale) based on the mean of the 3DMM shape model
            rho = initialRegistration(m.idMean[:, m.sourceLMInd], targetLandmarks)
            
            # Initialize the parameters: the shape coefficients are all 0, and we concatenate the similarity transform parameters at the end
            P = np.r_[np.zeros(m.numId + m.numExp), rho]
            
            # Find initial guess of shape coefficients while simulataneously optimizing the similarity transform paramters
            initFit = minimize(opt.initialShapeCost, P, args = (targetLandmarks, m, (wLan, wReg)), jac = opt.initialShapeGrad)
            P = initFit.x
            
            # You can use check_grad from scipy.optimize to make sure your analytical gradient is close to the numerical gradient
#            grad = check_grad(initialShapeCost, initialShapeGrad, P, targetLandmarks, m)
            
            # You can plot the 3DMM landmarks to check the initial shape parameter guess
#            source = generateFace(P, m)
#            plt.figure()
#            plt.imshow(imgScaled)
#            plt.scatter(source[0, m.sourceLMInd], source[1, m.sourceLMInd], s = 1)
        
        # For the following frames in the video, only do initial registration of similarity transform parameters
        else:
            P[-7:] = initialRegistration(generateFace(np.r_[P[:m.numId + m.numExp], np.zeros(6), 1], m, ind = m.sourceLMInd), targetLandmarks)
        
        '''
        Optimization
        '''
        
        # Initialize nearest neighbors fitter from scikit-learn to form correspondence between the target depth map points and the source (3DMM) vertices during the main optimization stage
        xv, yv = np.meshgrid(np.arange(192), np.arange(192))
        target = np.c_[xv.flatten(), yv.flatten(), depth.flatten()][np.flatnonzero(depth), :]
        NN = NearestNeighbors(n_neighbors = 1, metric = 'l2')
        NN.fit(target)
        
#        grad = check_grad(shapeCost, shapeGrad, P, m, target, targetLandmarks, NN, False)
        
        # For the first 20 frames, we learn the 3DMM shape identity parameters of the speaker in the video along with all the other parameters (this is set by the last the 'True' boolean argument)
        if frame <= 20:
            optFit = minimize(opt.shapeCost, P, args = (m, target, targetLandmarks, NN, (wVer, wLan, wReg), True), jac = opt.shapeGrad, options = {'maxiter': 40})
            P = optFit['x']
        
        # After the first 20 frames, we assume the shape identity parameters will be the same, so we can exclude them from the optimization to save time (note that the 'True' argument is now 'False')
        else:
            optFit = minimize(opt.shapeCost, P, args = (m, target, targetLandmarks, NN, (wVer, wLan, wReg), False), jac = opt.shapeGrad, options = {'maxiter': 40})
            P = optFit['x']
        
        # You can generate the vertices with a set of parameters and the model
#        source = generateFace(P, m)
        
        # You can orthographically plot the generated 3DMM over the VRN cropped and scaled image
#        plt.figure()
#        plt.imshow(imgScaled)
#        plt.scatter(source[0, :], source[1, :], s = 1)
        
        # Or you can just plot the landmarks of the generated 3DMM and save the plots too
#        plt.figure()
#        plt.imshow(imgScaled)
#        plt.scatter(source[0, m.sourceLMInd], source[1, m.sourceLMInd], s = 1)
#        plt.title(fName + '_' + str(case))
#        if not os.path.exists('landmarkOptPic'):
#            os.makedirs('landmarkOptPic')
#        savefig('landmarkOptPic/' + fName + '.png', bbox_inches='tight')
#        plt.close('all')
        
        """Transform, translate, and scale parameters for original image
        Because we learned the 3DMM parameters for the cropped and scaled version of the image produced by VRN, we do some simple transformations to change the similarity transform parameters so that the 3DMM can be orthographically projected onto the original image
        """
        
        # Save the parameters for the cropped/scaled image
        param[frame - 1, :] = P
        
        # Re-scale to original input image
        TS2orig[frame - 1, -1] = P[-1] / scale
        
        # Translate to account for original image dimensions
        # Case 1: The cropped picture is contained within the scaled image
        if (cropCorner >= 0).all() and ((192 + cropCorner) < scaledImgDim).all():
            TS2orig[frame - 1, :2] = (P[-4: -2] + cropCorner) / scale
        
        # Case 2: The crop corner is outside of the scaled image, but the extent of the cropped picture is within the bounds of the scaled image
        elif (cropCorner < 0).any() and ((192 + cropCorner) < scaledImgDim).all():
            TS2orig[frame - 1, :2] = (P[-4: -2] + cropCorner * (cropCorner > 0) + cropCorner * (cropCorner < 0) / 2) / scale
        
        # Case 3: The crop corner is outside of the scaled image, and the extent of the cropped picture is beyond the bounds of the scaled image
        elif (cropCorner < 0).any() and ((192 + cropCorner) > scaledImgDim).any():
            TS2orig[frame - 1, :2] = (P[-4: -2] + cropCorner * (cropCorner > 0) - (192 - (scaledImgDim - cropCorner * (cropCorner > 0))) / 2) / scale
        
        # You can now plot the 3DMM over the original image
        source = generateFace(np.r_[P[:m.numId + m.numExp + 3], TS2orig[frame - 1, :]], m)
        plt.figure()
        plt.imshow(imgOrig)
        plt.scatter(source[0, :], source[1, :], s = 1)
        
        plt.figure()
        plt.imshow(imgOrig)
        plt.scatter(source[0, m.sourceLMInd], source[1, m.sourceLMInd], s = 1)
        break

    """
    At the end of the loop, save the learned 3DMM parameters
    """
#    # These are the parameters to map the 3DMM to the VRN cropped and scaled image
#    np.save('temp/param', param)
#    
#    # These map the 3DMM to the original image
#    np.save('temp/paramRTS2Orig', np.c_[param[:, :m.numId + m.numExp + 3], TS2orig])
#    
#    # These are just the similarity transform parameters from the parameters above
#    np.save('temp/RTS', np.c_[param[:, -7: -4], TS2orig])
#    
#    # These are the 3DMM parameters in model space
#    np.save('temp/paramWithoutRTS', np.c_[param[:, :m.numId + m.numExp], np.zeros((numFrames, 6)), np.ones(numFrames)])
    
    """
    You can export .obj files for each frame
    """
#    # In this case, we save .obj files for the 3DMM with parameters mapping to the original image
#    param = np.load('paramRTS2Orig.npy')
#    if not os.path.exists('shapes'):
#        os.makedirs('shapes')
#    for shape in range(numFrames):
#        fName = '{:0>5}'.format(shape + 1)
#        exportObj(generateFace(np.r_[param[shape, :m.numId + m.numExp], np.zeros(6), 1], m), f = m.face, fNameOut = 'shapes/' + fName)

    """
    You can use Mayavi to make an animation of the learned 3DMMs
    """
#    os.environ["QT_API"] = "pyqt"
#    from mayavi import mlab
#    param = np.load('paramWithoutRTS.npy')
#    shape = generateFace(np.r_[param[0, :m.numId + m.numExp], np.zeros(6), 1], m)
#    tmesh = mlab.triangular_mesh(shape[0, :], shape[1, :], shape[2, :], m.face, scalars = np.arange(m.numVertices), color = (1, 1, 1))
##    view = mlab.view()
#    
#    if not os.path.exists('shapePic'):
#        os.makedirs('shapePic')
#    for frame in range(100):
#        fName = '{:0>5}'.format(frame + 1)
#        shape = generateFace(np.r_[param[frame, :m.numId + m.numExp], np.zeros(6), 1], m)
#        
#        tmesh = mlab.triangular_mesh(shape[0, :], shape[1, :], shape[2, :], m.face, scalars = np.arange(m.numVertices), color = (1, 1, 1))
#        mlab.view(view[0], view[1], view[2], view[3])
#        mlab.savefig('shapePic/' + fName + '.png', figure = mlab.gcf())
#        mlab.close(all = True)

    """
    This example shows one of the downfalls of using VRN
    """
#    depth = np.load('/home/leon/f2f-fitting/data/kao3/depth/Adam_Freier_0001.npy')

#    fig = plt.figure()
#    ax = plt.axes(projection='3d')
#    xv, yv = np.meshgrid(np.arange(192), np.arange(192))
#    ax.scatter(xv, yv, depth, s = 0.1, c = 'b')
#    ax.set_xlabel('X')
#    ax.set_ylabel('Y')
#    ax.set_zlabel('Z')