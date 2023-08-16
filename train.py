# train.py

import torch
import torchaudio
import auraloss
import numpy as np
from torchinfo import summary

from torch.utils.tensorboard import SummaryWriter
from datetime import datetime
from pathlib import Path

from src.helpers import load_data, select_device, initialize_model, save_model_checkpoint
from configurations import parse_args, configs


def main():
    args = parse_args()

    torch.manual_seed(42)
    torch.cuda.empty_cache()            
    torch.backends.cudnn.benchmark = True

    device = select_device(args.device)

     # Find the configuration in the list
    print(f"Using configuration {args.config}")
    sel_config = next((c for c in configs if c['conf_name'] == args.config), None)
    if sel_config is None:
        raise ValueError('Configuration not found')
    hparams = sel_config

    # Initialize model
    model, rf, params = initialize_model(device, hparams)

    # Initialize Tensorboard writer
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = Path(args.logdir) / f"train/{hparams['conf_name']}_{args.n_epochs}_{args.batch_size}_{args.lr}_{timestamp}"
    writer = SummaryWriter(log_dir=log_dir)
    writer.add_text('model_summary', str(model), global_step=0)

    torch.cuda.empty_cache()

    # Define loss function and optimizer
    mae = torch.nn.L1Loss().to(device)
    mse = torch.nn.MSELoss().to(device)
    esr = auraloss.time.ESRLoss().to(device)
    mrstft = auraloss.freq.MultiResolutionSTFTLoss(
        fft_sizes=[32, 128, 512, 2048],
        win_lengths=[32, 128, 512, 2048],
        hop_sizes=[16, 64, 256, 1024]).to(device)
    dc = auraloss.time.DCLoss().to(device)

    criterion = mrstft
    criterion_str = 'mrstft'

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    ms1 = int(args.n_epochs * 0.6)
    ms2 = int(args.n_epochs * 0.8)
    milestones = [ms1, ms2]
    
    scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer, milestones, gamma=0.1,verbose=False)
    
    # Load data
    train_loader, valid_loader, _ = load_data(args.datadir, args.batch_size)
    
    # Initialize minimum validation loss with infinity
    min_valid_loss = np.inf
    # patience_counter = 0

    hparams.update({
        'n_epochs': args.n_epochs,
        'batch_size': args.batch_size,
        'lr': args.lr,
        'receptive_field': rf,
        'params': params,
        'criterion': criterion_str,
    })

    print(f"Training model for {args.n_epochs} epochs, with batch size {args.batch_size} and learning rate {args.lr}")
    try:
        for epoch in range(args.n_epochs):
            train_loss = 0.0

            # Training
            model.train()
            c = torch.tensor([0.0, 0.0]).view(1,1,-1).to(device)
            for batch_idx, (dry, wet) in enumerate(train_loader):
                optimizer.zero_grad() 
                input = dry.to(device)
                target = wet.to(device)
            
                output = model(input, c)
                
                output = torchaudio.functional.preemphasis(output, 0.95)
                loss = criterion(output, target)        
                
                loss.backward()                             
                optimizer.step()
         
                train_loss += loss.item()
                
                lr = optimizer.param_groups[0]['lr']
                writer.add_scalar('training/learning_rate', lr, global_step=epoch)

            avg_train_loss = train_loss / len(train_loader)
            
            writer.add_scalar('training/loss', avg_train_loss, global_step=epoch)
            
            # Validation
            model.eval()
            valid_loss = 0.0
            with torch.no_grad():
                for step, (dry, wet) in enumerate(valid_loader):
                    input = dry.to(device)
                    target = wet.to(device)
                
                    output = model(input, c)
                    
                    output = torchaudio.functional.preemphasis(output, 0.95)
                    loss = criterion(output, target)
                    
                    valid_loss += loss.item()                   
                avg_valid_loss = valid_loss / len(valid_loader)    
    
            writer.add_scalar('validation/loss', avg_valid_loss, global_step=epoch)

            scheduler.step(avg_valid_loss) # Update learning rate

            # Save the model if it improved
            if avg_valid_loss < min_valid_loss:
                print(f"Epoch {epoch}: Loss improved from {min_valid_loss:4f} to {avg_valid_loss:4f} - > Saving model", end="\r")
                
                min_valid_loss = avg_valid_loss
                save_model_checkpoint(
                    model, hparams, criterion_str, optimizer, scheduler, args.n_epochs, args.batch_size, args.lr, timestamp, args
                )
                patience_counter = 0  # reset the counter if performance improved
            else:
                patience_counter += 1  # increase the counter if performance did not improve

            # # Early stopping if performance did not improve after n epochs
            # if patience_counter >= 20:
            #     print(f"Early stopping triggered after {patience_counter} epochs without improvement in validation loss.")
            #     break
    finally:
        final_train_loss = avg_train_loss
        final_valid_loss = avg_valid_loss
        writer.add_hparams(hparams, {'Final Training Loss': final_train_loss, 'Final Validation Loss': final_valid_loss})
        print(f"Final Validation Loss: {final_valid_loss}")
        single_output = output[0].detach().cpu()
        abs_max = torch.max(torch.abs(single_output))
        # Avoid division by zero: if abs_max is 0, just set it to 1
        if abs_max == 0:
            abs_max = 1
        # Normalize waveform to range [-1, 1]
        normalized_output = single_output / abs_max

        # Save the normalized waveform
        save_path = f"{log_dir}/{args.config}_output.wav"
        torchaudio.save(save_path, normalized_output, args.sample_rate)

    writer.close()

if __name__ == "__main__":
    main()