//
// ********************************************************************
// * License and Disclaimer                                           *
// *                                                                  *
// * The  Geant4 software  is  copyright of the Copyright Holders  of *
// * the Geant4 Collaboration.  It is provided  under  the terms  and *
// * conditions of the Geant4 Software License,  included in the file *
// * LICENSE and available at  http://cern.ch/geant4/license .  These *
// * include a list of copyright holders.                             *
// *                                                                  *
// * Neither the authors of this software system, nor their employing *
// * institutes,nor the agencies providing financial support for this *
// * work  make  any representation or  warranty, express or implied, *
// * regarding  this  software system or assume any liability for its *
// * use.  Please see the license in the file  LICENSE  and URL above *
// * for the full disclaimer and the limitation of liability.         *
// *                                                                  *
// * This  code  implementation is the result of  the  scientific and *
// * technical work of the GEANT4 collaboration.                      *
// * By using,  copying,  modifying or  distributing the software (or *
// * any work based  on the software)  you  agree  to acknowledge its *
// * use  in  resulting  scientific  publications,  and indicate your *
// * acceptance of all terms of the Geant4 Software license.          *
// ********************************************************************
//
/// \file hadronic/Hadr03/src/PhysicsList.cc
/// \brief Implementation of the PhysicsList class
//
// $Id: PhysicsList.cc 96284 2016-04-04 07:19:26Z gcosmo $

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

#include "PhysicsList.hh"

#include "G4SystemOfUnits.hh"
#include "G4UnitsTable.hh"

#include "G4HadronElasticPhysicsHP.hh"

#include "G4HadronPhysicsFTFP_BERT_HP.hh"
#include "G4HadronPhysicsQGSP_BIC_HP.hh"
#include "G4HadronPhysicsQGSP_BIC_AllHP.hh"
#include "G4HadronInelasticQBBC.hh"
#include "G4HadronPhysicsINCLXX.hh"
#include "G4HadronPhysicsQGSP_BERT.hh"
#include "G4HadronPhysicsFTFP_BERT.hh"

#include "G4IonElasticPhysics.hh"
#include "G4EmExtraPhysics.hh"
#include "G4IonPhysics.hh"
#include "G4IonINCLXXPhysics.hh"
#include "G4IonBinaryCascadePhysics.hh"
#include "G4IonPhysicsPHP.hh"
#include "G4IonQMDPhysics.hh"

// particles

#include "G4BosonConstructor.hh"
#include "G4LeptonConstructor.hh"
#include "G4MesonConstructor.hh"
#include "G4BosonConstructor.hh"
#include "G4BaryonConstructor.hh"
#include "G4IonConstructor.hh"
#include "G4ShortLivedConstructor.hh"
#include "PhysicsListMessenger.hh"

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

PhysicsList::PhysicsList()
  :G4VModularPhysicsList()
{
  
  //add new units for cross sections
  // 
  new G4UnitDefinition( "mm2/g",  "mm2/g", "Surface/Mass", mm2/g);
  new G4UnitDefinition( "um2/mg", "um2/mg","Surface/Mass", um*um/mg);  

  messenger = new PhysicsListMessenger(this);
  
 
}

void PhysicsList::ConstructProcess()
{
   // Transportation
    //
    AddTransportation();

    for(size_t i=0; i < hadronPhys.size(); i++)
      {
        hadronPhys[i] -> ConstructProcess();
      }

    return;
}
  
void PhysicsList::AddPhysicsList(const G4String& name)
{
  G4int verb = 2;  
  SetVerboseLevel(verb);

  // Ion Elastic scattering
  hadronPhys.push_back(new G4IonElasticPhysics(verb));
  
  hadronPhys.push_back(new G4EmExtraPhysics());
  
  if (verb>1) {
    G4cout << "PhysicsList::AddPhysicsList: <" << name << ">" << G4endl;
  }

  if (name == "def" || name == "default")
    {
      // hadronPhys.push_back(new G4HadronElasticPhysicsHP(verb));
      // hadronPhys.push_back(new G4IonElasticPhysics(verb));  
      hadronPhys.push_back(new G4IonPhysics(verb));
    }
  else if (name == "bert")
    {
      //non ha interazioni fra ioni a quest'energia
      hadronPhys.push_back(new G4HadronPhysicsFTFP_BERT_HP(verb));
    }
  else if (name == "bic")
    {
      hadronPhys.push_back(new G4IonBinaryCascadePhysics(verb));
      hadronPhys.push_back(new G4HadronPhysicsQGSP_BIC_HP(verb));
    }
  else if (name == "qmd")
    {
      hadronPhys.push_back(new G4IonQMDPhysics(verb));
    }
  else if (name == "incl")
    {
      hadronPhys.push_back(new G4HadronPhysicsINCLXX(verb));
      hadronPhys.push_back(new G4IonINCLXXPhysics(verb));
    }
  else if (name == "incl-ftfp")
    {
      G4HadronPhysicsINCLXX* hp = new G4HadronPhysicsINCLXX("hInelastic INCLXX with FTFP",true,false,true);
      hp->SetVerboseLevel(verb);
      hadronPhys.push_back(hp);
      hadronPhys.push_back(new G4IonINCLXXPhysics(verb));
    }
  else if (name == "php")
    {
      //non ha interazioni fra ioni a quest'energia      
      hadronPhys.push_back(new G4IonPhysicsPHP(verb));
    }
  else if (name == "allHP" || name == "AllHP")
    {
      hadronPhys.push_back(new G4HadronPhysicsQGSP_BIC_AllHP(verb));
    }
  else if (name == "qgsp")
    {
      hadronPhys.push_back(new G4HadronPhysicsQGSP_BERT(verb));
    }
  else if (name == "ftfp")
    {
      hadronPhys.push_back(new G4HadronPhysicsFTFP_BERT(verb));
    }
  else
    {
      G4cout << "PhysicsList::AddPhysicsList: <" << name << ">"
	     << " is not defined"
	     << G4endl;
      exit(-1);
    }
  // Hadron Elastic scattering
  //

    
  G4cout<<__FILE__<<" "<<__func__<<" "<<hadronPhys.size()<<" hadronic models had been registered: "<<G4endl;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

PhysicsList::~PhysicsList()
{
  delete messenger;
  for(size_t i=0; i<hadronPhys.size(); i++)
    {
      delete hadronPhys[i];
    }
  hadronPhys.clear();
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void PhysicsList::ConstructParticle()
{
  G4BosonConstructor  pBosonConstructor;
  pBosonConstructor.ConstructParticle();

  G4LeptonConstructor pLeptonConstructor;
  pLeptonConstructor.ConstructParticle();

  G4MesonConstructor pMesonConstructor;
  pMesonConstructor.ConstructParticle();

  G4BaryonConstructor pBaryonConstructor;
  pBaryonConstructor.ConstructParticle();

  G4IonConstructor pIonConstructor;
  pIonConstructor.ConstructParticle();

  G4ShortLivedConstructor pShortLivedConstructor;
  pShortLivedConstructor.ConstructParticle();  
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void PhysicsList::SetCuts()
{
  SetCutValue(0*mm, "proton");
}

