import os
import numpy
import sys
import logging
import datetime
import gc 
from apgl.util.PathDefaults import PathDefaults
from apgl.util.Util import Util
from sandbox.ranking.TreeRank import TreeRank
from sandbox.ranking.TreeRankForest import TreeRankForest
from wallhack.metabolomics.MetabolomicsUtils import MetabolomicsUtils
from sandbox.data.Standardiser import Standardiser
from sandbox.ranking.leafrank.SVMLeafRank import SVMLeafRank
from sandbox.ranking.leafrank.DecisionTree import DecisionTree
from sandbox.ranking.RankSVM import RankSVM
from sandbox.ranking.RankBoost import RankBoost

class MetabolomicsExpRunner(object):
    def __init__(self, YList, X, featuresName, ages, args):
        """
        Create a new object 
        
        :param YList: A list of labels 
        
        :param X: the features 
        
        :param featureName: The name of the feature 
        
        :param ages: The ages 
        
        :
        """
        super(MetabolomicsExpRunner, self).__init__(args=args)
        self.X = X
        self.YList = YList #The list of concentrations 
        self.featuresName = featuresName
        self.args = args
        self.ages = ages 

        self.maxDepth = 10
        self.numTrees = 10
        self.sampleSize = 1.0
        self.sampleReplace = True
        self.folds = 5
        self.resultsDir = PathDefaults.getOutputDir() + "metabolomics/"

        self.leafRankGenerators = []
        self.leafRankGenerators.append((SVMLeafRank.generate(), "SVM"))
        self.leafRankGenerators.append((DecisionTree.generate(), "CART"))


        #Store all the label vectors and their missing values
        YIgf1Inds, YICortisolInds, YTestoInds = MetabolomicsUtils.createIndicatorLabels(YList)
        self.hormoneInds = [YIgf1Inds, YICortisolInds, YTestoInds]
        self.hormoneNames = MetabolomicsUtils.getLabelNames()

    def saveResult(self, X, Y, learner, fileName):
        """
        Save a single result to file, checking if the results have already been computed
        """
        fileBaseName, sep, ext = fileName.rpartition(".")
        lockFileName = fileBaseName + ".lock"
        gc.collect()

        if not os.path.isfile(fileName) and not os.path.isfile(lockFileName):
            try:
                lockFile = open(lockFileName, 'w')
                lockFile.close()
                logging.debug("Created lock file " + lockFileName)

                logging.debug("Computing file " + fileName)
                logging.debug(learner)
                (bestParams, allMetrics, bestMetaDicts) = learner.evaluateCvOuter(X, Y, self.folds)
                cvResults = {"bestParams":bestParams, "allMetrics":allMetrics, "metaDicts":bestMetaDicts}
                Util.savePickle(cvResults, fileName)
                
                os.remove(lockFileName)
                logging.debug("Deleted lock file " + lockFileName)
            except:
                logging.debug("Caught an error in the code ... skipping")
                raise
        else:
            logging.debug("File exists, or is locked: " + fileName)

    def saveResults(self, leafRankGenerators, mode="std"):
        """
        Compute the results and save them for a particular hormone. Does so for all
        leafranks
        """
        for j in range(len(self.hormoneInds)):
            nonNaInds = self.YList[j][1]
            hormoneInd = self.hormoneInds[j]

            for k in range(len(hormoneInd)):
                if type(self.X) == numpy.ndarray:
                    X = self.X[nonNaInds, :]
                else:
                    X = self.X[j][nonNaInds, :]
                X = numpy.c_[X, self.ages[nonNaInds]]

                if mode != "func":
                    X = Standardiser().standardiseArray(X)
                    
                Y = hormoneInd[k]
                waveletInds = numpy.arange(X.shape[1]-1)

                logging.debug("Shape of examples: " + str(X.shape))
                logging.debug("Distribution of labels: " + str(numpy.bincount(Y)))

                #Go through all the leafRanks
                for i in range(len(leafRankGenerators)):

                    leafRankName = leafRankGenerators[i][1]
                    if mode != "func":
                        leafRankGenerator = leafRankGenerators[i][0]
                    else:
                        leafRankGenerator = leafRankGenerators[i][0](waveletInds)

                    fileName = self.resultsDir + "TreeRank-" + self.hormoneNames[j] + "_" + str(k) + "-" +  leafRankName  + "-" + self.featuresName +  ".dat"
                    treeRank = TreeRank(leafRankGenerator)
                    treeRank.setMaxDepth(self.maxDepth)
                    self.saveResult(X, Y, treeRank, fileName)

                    fileName = self.resultsDir + "TreeRankForest-" + self.hormoneNames[j] + "_" + str(k) + "-" +  leafRankName  + "-" + self.featuresName +  ".dat"
                    treeRankForest = TreeRankForest(leafRankGenerator)
                    treeRankForest.setMaxDepth(self.maxDepth)
                    treeRankForest.setNumTrees(self.numTrees)
                    
                    treeRankForest.setSampleReplace(self.sampleReplace)
                    #Set the number of features to be the root of the total number if not functional
                    if mode == "std":
                        treeRankForest.setFeatureSize(numpy.round(numpy.sqrt(X.shape[1]))/float(X.shape[1]))
                    else:
                        treeRankForest.setFeatureSize(1.0)
                        
                    
                    self.saveResult(X, Y, treeRankForest, fileName)

                if mode == "std":
                    #Run RankSVM
                    fileName = self.resultsDir + "RankSVM-" + self.hormoneNames[j] + "_" + str(k)  + "-" + self.featuresName +  ".dat"
                    rankSVM = RankSVM()
                    self.saveResult(X, Y, rankSVM, fileName)

                    #fileName = self.resultsDir + "RBF-RankSVM-" + self.hormoneNames[j] + "_" + str(k)  + "-" + self.featuresName +  ".dat"
                    #rankSVM = RankSVM()
                    #rankSVM.setKernel("rbf")
                    #self.saveResult(X, Y, rankSVM, fileName)

                    #Run RankBoost
                    fileName = self.resultsDir + "RankBoost-" + self.hormoneNames[j] + "_" + str(k)  + "-" + self.featuresName +  ".dat"
                    rankBoost = RankBoost()
                    self.saveResult(X, Y, rankBoost, fileName)
                        
    def run(self):
        logging.debug('module name:' + __name__) 
        logging.debug('parent process:' +  str(os.getppid()))
        logging.debug('process id:' +  str(os.getpid()))

        self.saveResults(self.leafRankGenerators, "std")
